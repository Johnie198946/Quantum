"""Manual Feishu QuanSyn commands on the existing Hermes execution lifecycle."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import httpx

COMMAND = re.compile(r"(查看|绑定|拉取并执行|拉取|执行|推送)\s*QuanSyn(?:\s+(\S+))?(?:\s+附件\s+([0-9,，]+))?", re.I)
ID = re.compile(r"qs_[a-f0-9]{32}")


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class MacKeychain:
    """Credentials stay in the macOS login Keychain, never plugin JSON/model input."""
    service = "com.quantum.quansyn"

    def get(self, account):
        result = subprocess.run(["/usr/bin/security", "find-generic-password", "-a", account,
                                 "-s", self.service, "-w"], capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise ValueError("请先在 Web 连接 Mac，并发送绑定 QuanSyn 配对码")
        return result.stdout.strip()

    def set(self, account, token):
        result = subprocess.run(["/usr/bin/security", "add-generic-password", "-U", "-a", account,
                                 "-s", self.service, "-w", token], capture_output=True, timeout=10)
        if result.returncode:
            raise ValueError("无法写入 Mac Keychain，绑定未在本机完成；请在 Web 撤销后重试")


class QuanSyn:
    def __init__(self, ctx, owner_check=None):
        self.ctx = ctx
        self.owner_check = owner_check or (lambda platform, sender: False)
        self.credentials = MacKeychain()
        self.turns = {}
        self.delivery = {}
        if callable(getattr(ctx, "register_hook", None)):
            ctx.register_hook("pre_gateway_dispatch", self.gateway)

    def gateway(self, event=None, gateway=None, **kw):
        source = getattr(event, "source", None)
        platform = getattr(source, "platform", "")
        if str(getattr(platform, "value", platform)).lower() not in {"feishu", "lark"}:
            return None
        text = str(getattr(event, "text", "") or "").strip()
        native = getattr(getattr(event, "raw_message", None), "event", None)
        value = getattr(getattr(native, "action", None), "value", None)
        card = isinstance(value, dict) and "quansyn_command" in value
        if not card and text.lower() != "quansyn" and not COMMAND.fullmatch(text):
            return None
        if getattr(source, "chat_type", "") != "dm":
            return {"action": "skip", "reason": "quansyn_private_chat_only"}
        sender = str(getattr(source, "user_id", "") or "")
        if not sender or not self.owner_check(str(getattr(platform, "value", platform)), sender):
            return {"action": "skip", "reason": "quansyn_local_owner_required"}
        if card:
            operator = str(getattr(getattr(native, "operator", None), "open_id", "") or "")
            if (not operator or operator not in {sender, getattr(source, "user_id_alt", None)}
                    or value.get("sender_id") != sender):
                return {"action": "skip", "reason": "quansyn_card_owner_mismatch"}
            text = str(value.get("quansyn_command", ""))
            if not COMMAND.fullmatch(text) or text.startswith("绑定"):
                return {"action": "skip", "reason": "quansyn_invalid_card_command"}
        elif text.lower() == "quansyn":
            text = "查看 QuanSyn"
        adapter = getattr(gateway, "adapters", {}).get(platform)
        if adapter is not None:
            if len(self.delivery) >= 128 and sender not in self.delivery:
                self.delivery.clear()
            self.delivery[sender] = (adapter, str(source.chat_id))
        return {"action": "rewrite", "text": text}

    def card(self, turn):
        sender = turn["sender"]
        def button(label, command, primary=False):
            return {"tag": "button", "text": {"tag": "plain_text", "content": label},
                    "type": "primary" if primary else "default",
                    "value": {"quansyn_command": command, "sender_id": sender}}
        elements = []
        if "rows" in turn:
            rows = turn["rows"]
            for row in rows[:10]:
                elements.append({"tag": "markdown", "content":
                    f'**待处理需求**\n{row["text"][:300]}\n附件：{len(row["files"])} 个 · `{row["id"]}`'})
                elements.append({"tag": "action", "actions": [
                    button("拉取并执行", "拉取并执行 QuanSyn " + row["id"], True),
                    button("仅拉取", "拉取 QuanSyn " + row["id"]) ]})
            if not rows:
                elements.append({"tag": "markdown", "content": "暂无发给 Mac 的待处理需求。"})
            elif len(rows) > 10:
                elements.append({"tag": "markdown", "content": "先显示前10条，处理后刷新查看其余需求。"})
        else:
            elements.append({"tag": "markdown", "content": str(turn.get("reply") or "执行已完成，可回传完整结果。")[:600]})
            transfer = turn.get("id")
            if transfer and ID.fullmatch(transfer) and not turn.get("failed"):
                saved = self.ctx.state.get(self.key(sender, transfer), {})
                if saved.get("completed"):
                    names = "、".join(Path(f["path"]).name for f in saved.get("outputs", []))
                    elements.append({"tag": "markdown", "content": "生成附件：" + (names[:500] or "无")})
                    elements.append({"tag": "action", "actions": [button("推送完整结果到 QuanSyn", "推送 QuanSyn " + transfer, True)]})
                elif saved.get("imported") and turn.get("action") == "拉取":
                    elements.append({"tag": "action", "actions": [button("开始执行", "执行 QuanSyn " + transfer, True)]})
        elements.append({"tag": "action", "actions": [button("刷新待处理", "查看 QuanSyn"),
            {"tag": "button", "text": {"tag": "plain_text", "content": "打开 QuanSyn"},
             "type": "default", "url": self.base() + "/quansyn/"}]})
        return {"config": {"wide_screen_mode": True},
                "header": {"template": "red" if turn.get("failed") else "blue",
                           "title": {"tag": "plain_text", "content": "Quantum · QuanSyn"}},
                "elements": elements}

    def deliver_card(self, turn):
        route = self.delivery.get(turn["sender"])
        if route is None:
            return False
        adapter, chat_id = route
        loop = getattr(adapter, "_loop", None)
        if loop is None or not loop.is_running():
            return False
        try:
            if asyncio.get_running_loop() is loop:
                return False
        except RuntimeError:
            pass
        async def send():
            response = await adapter._feishu_send_with_retry(chat_id=chat_id,
                msg_type="interactive", payload=json.dumps(self.card(turn), ensure_ascii=False),
                reply_to=None, metadata=None)
            return adapter._finalize_send_result(response, "QuanSyn card failed").success
        future = asyncio.run_coroutine_threadsafe(send(), loop)
        try:
            return bool(future.result(timeout=15))
        except Exception:
            future.cancel()
            return False

    def base(self):
        value = str(self.ctx.get_config("quansyn.api_base", "") or os.environ.get("QUANSYN_API_BASE_URL", "")).rstrip("/")
        parts = urlsplit(value)
        if (parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1"})) or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("需配置 quansyn.api_base 为 QuanSyn HTTPS 地址（本地验收可使用 localhost）")
        return value

    def account(self, sender):
        return digest(self.base() + "\0" + sender)

    def key(self, sender, transfer):
        return "quansyn:" + digest(sender + "\0" + transfer)

    def root(self, sender, transfer):
        root = self.ctx.state.data_dir / "quansyn" / digest(sender + "\0" + transfer)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        return root.resolve()

    def http(self, sender, method, path, *, payload=None, data=None, filename=None, public=False, sink=None):
        headers = {} if public else {"Authorization": "Bearer " + self.credentials.get(self.account(sender)), "X-QuanSyn-Sender": sender}
        if filename:
            from urllib.parse import quote
            headers["X-File-Name"] = quote(filename, safe="")
            headers["Content-Type"] = "application/octet-stream"
        if hasattr(data, "read"):
            source = data
            data = iter(lambda: source.read(1024 * 1024), b"")
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            if path.startswith("/files/") and method == "GET":
                with client.stream(method, self.base() + "/api/v1/quansyn" + path, headers=headers) as response:
                    if response.status_code >= 300:
                        raise ValueError(f"QuanSyn 请求失败（HTTP {response.status_code}），未确认成功")
                    raw = bytearray()
                    content_hash = hashlib.sha256()
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        content_hash.update(chunk)
                        if sink is not None:
                            sink.write(chunk)
                        else:
                            raw.extend(chunk)
                    return content_hash.hexdigest() if sink is not None else bytes(raw)
            response = client.request(method, self.base() + "/api/v1/quansyn" + path,
                                      headers=headers, json=payload, content=data)
        if response.status_code >= 300:
            # Never include request headers or credentials in errors/model context.
            raise ValueError(f"QuanSyn 请求失败（HTTP {response.status_code}），未确认成功")
        return response.json()

    def pull(self, sender, transfer):
        key = self.key(sender, transfer)
        saved = self.ctx.state.get(key, {})
        row = self.http(sender, "GET", "/transfers/" + transfer)
        if row["direction"] != "request" or row["target"] != "mac":
            raise ValueError("请选择发给 Mac 的需求")
        if saved.get("imported"):
            return saved
        if row["status"] in {"claimed", "imported", "returned"} and saved.get("claim") and "files" in saved and "text" in saved:
            for file in saved["files"]:
                with Path(file["path"]).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != file["hash"]:
                        raise ValueError("本地附件哈希不符，未确认导入")
            self.http(sender, "POST", f"/transfers/{transfer}/imported", payload={"revision": row["revision"], "claim": saved["claim"]})
            saved["imported"] = True
            self.ctx.state.set(key, saved)
            return saved
        claim = saved.get("claim") or secrets.token_urlsafe(32)
        saved.update(claim=claim, id=transfer, sender=sender)
        self.ctx.state.set(key, saved)
        leased = self.http(sender, "POST", f"/transfers/{transfer}/claim", payload={"revision": row["revision"], "claim": claim})
        local_files = []
        for index, file in enumerate(row["files"]):
            name = Path(file.get("metadata", {}).get("original_name") or file["filename"]).name
            destination = self.root(sender, transfer) / f"{index + 1}-{name}"
            if not destination.resolve().is_relative_to(self.root(sender, transfer)):
                raise ValueError("附件路径越界")
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                content_hash = self.http(sender, "GET", "/files/" + file["artifact_id"], sink=stream)
                stream.flush()
                os.fsync(stream.fileno())
            if content_hash != file["content_hash"]:
                raise ValueError("附件哈希不符，未确认导入")
            local_files.append({"path": str(destination), "name": name, "hash": file["content_hash"]})
        saved.update(text=row["text"], blocks=row["blocks"], files=local_files, imported=False)
        self.ctx.state.set(key, saved)
        self.http(sender, "POST", f"/transfers/{transfer}/imported", payload={"revision": leased["revision"], "claim": claim})
        saved["imported"] = True
        self.ctx.state.set(key, saved)
        return saved

    def before_turn(self, user_message="", **kw):
        platform = str(getattr(kw.get("platform"), "value", kw.get("platform")) or "").lower()
        session = str(kw.get("session_id") or "")
        sender = str(kw.get("sender_id") or "")
        if platform not in {"feishu", "lark"} or not session or not sender or not self.owner_check(platform, sender):
            return None
        # Human command must be the entire trusted gateway message, not quoted instructions in content.
        match = COMMAND.fullmatch(user_message.strip())
        if not match:
            self.turns.pop(session, None)
            return None
        if len(self.turns) >= 128:
            self.turns.clear()
        action, transfer, selection = match.groups()
        turn = {"sender": sender, "action": action, "id": transfer, "turn_id": kw.get("turn_id"), "reply": None}
        self.turns[session] = turn
        turn["selection"] = selection
        return {"context": "用户已明确授权当前 QuanSyn 指令。必须调用 ai_lab_execute capability=quansyn inputs={action:command} 获取真实回执。成功领取并执行时，按照返回 goal 在现有 Hermes 中执行。不要自行构造配对、账号、文件或回传状态。"}

    def pre_tool(self, tool_name, args=None, **kw):
        if tool_name != "ai_lab_execute:quansyn":
            return None
        turn = self.turns.get(str(kw.get("session_id") or ""), {})
        action = (args or {}).get("inputs", {}).get("action")
        if not turn or not turn.get("turn_id") or kw.get("turn_id") != turn["turn_id"] or action not in {"command", "outputs"}:
            return {"action": "block", "message": "QuanSyn 缺少当前回合的可信用户指令"}
        if action == "outputs" and not turn.get("executing"):
            return {"action": "block", "message": "QuanSyn 尚未开始执行，不能登记输出"}
        # Native Hermes omits turn_id at handler dispatch; its trusted pre-tool hook supplies admission.
        turn.setdefault("admitted", set()).add(action)
        return None

    def authorized(self, turn, action, kw):
        if not turn or not turn.get("turn_id"):
            return False
        if kw.get("turn_id"):
            return kw["turn_id"] == turn["turn_id"]
        admitted = turn.get("admitted", set())
        if action not in admitted:
            return False
        admitted.remove(action)
        return True

    def command(self, **kw):
        session = str(kw.get("session_id") or "")
        turn = self.turns.get(session, {})
        if not self.authorized(turn, "command", kw):
            raise ValueError("缺少本回合可信 QuanSyn 指令")
        if turn.get("command_result") is not None:
            return turn["command_result"]
        result = self._command(turn)
        turn["command_result"] = result
        return result

    def _command(self, turn):
        sender, action, transfer, selection = turn["sender"], turn["action"], turn["id"], turn["selection"]
        try:
            if action == "绑定":
                paired = self.http(sender, "POST", "/devices/exchange", public=True, payload={"code": transfer, "sender_id": sender})
                self.credentials.set(self.account(sender), paired["token"])
                turn["reply"] = "QuanSyn 已绑定。发送“查看 QuanSyn”即可读取发给 Mac 的需求；可在 Web 撤销权限。"
            elif action == "查看":
                rows = self.http(sender, "GET", "/transfers?target=mac&pending=true")["items"]
                turn["rows"] = rows
                turn["reply"] = "\n".join(f'{r["id"]} · {r["text"][:100]} · {len(r["files"])} 个附件' for r in rows) or "暂无发给 Mac 的待处理需求。"
            elif not transfer or not ID.fullmatch(transfer):
                raise ValueError("请提供完整需求编号 qs_…")
            elif action == "推送":
                saved = self.ctx.state.get(self.key(sender, transfer), {})
                if not saved.get("result") or not saved.get("completed"):
                    raise ValueError("该需求还没有已完成的运行结果")
                staged = saved.get("outputs", [])
                chosen = sorted(set(int(x) - 1 for x in selection.replace("，", ",").split(","))) if selection else list(range(len(staged)))
                files = []
                for index in chosen:
                    if index < 0 or index >= len(staged):
                        raise ValueError("附件编号不存在")
                    file = staged[index]
                    path = Path(file["path"])
                    root = self.root(sender, transfer)
                    if not path.resolve().is_relative_to(root) or path.is_symlink():
                        raise ValueError("输出文件路径越界")
                    with open(path, "rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != file["hash"]:
                            raise ValueError("输出文件已改变，请重新执行并确认")
                        stream.seek(0)
                        receipt = self.http(sender, "POST", "/files", data=stream, filename=path.name)
                    files.append({"artifact_id": receipt["artifact_id"]})
                receipt = self.http(sender, "POST", "/transfers", payload={
                    "request_id": "mac-" + digest(transfer + saved["result"] + json.dumps(files, sort_keys=True)),
                    "direction": "result", "target": "mac", "reply_to": transfer,
                    "text": saved["result"], "blocks": saved.get("result_blocks", []), "files": files,
                })
                turn["reply"] = f'已回传 QuanSyn：{receipt["id"]}，包含 {len(files)} 个附件。'
            else:
                saved = self.pull(sender, transfer) if action in {"拉取", "拉取并执行"} else self.ctx.state.get(self.key(sender, transfer), {})
                if not saved.get("imported"):
                    raise ValueError("请先拉取该需求")
                if action == "拉取":
                    turn["reply"] = f'已拉取 {transfer}：\n{saved["text"]}\n附件：\n' + "\n".join(f['path'] for f in saved["files"]) + f"\n发送“执行 QuanSyn {transfer}”开始运行。"
                elif saved.get("completed"):
                    turn["reply"] = "该需求已执行完成，可直接回传已有完整结果，无需重新执行。"
                else:
                    turn["executing"] = True
                    saved["completed"] = False
                    saved["outputs"] = []
                    self.ctx.state.set(self.key(sender, transfer), saved)
                    return {"success": True, "goal": {
                        "request": saved["text"], "blocks": saved["blocks"], "files": saved["files"],
                        "output_directory": str(self.root(sender, transfer)),
                        "instruction": "沿用当前工具完成需求；输出文件保存在 output_directory。使用 ai_lab_execute capability=quansyn action=outputs 登记生成的文件。不要自动回传。",
                    }}
        except Exception as exc:
            turn["failed"] = True
            turn["reply"] = str(exc) if isinstance(exc, ValueError) else "QuanSyn 操作失败，未确认成功，请检查连接或重试。"
        return {"success": not turn.get("failed", False), "receipt": turn["reply"]}

    def outputs(self, inputs, **kw):
        session = str(kw.get("session_id") or "")
        turn = self.turns.get(session, {})
        if not turn.get("executing") or not self.authorized(turn, "outputs", kw):
            raise ValueError("只有当前可信执行回合可以登记输出")
        paths = inputs.get("paths", [])
        blocks = inputs.get("blocks", [])
        if not isinstance(paths, list) or len(paths) > 10:
            raise ValueError("最多登记 10 个文件")
        # Installed packages include an exact copy of the canonical server contract.
        try:
            from ._quansyn_contract import Block
        except ImportError:
            from backend.contracts.quansyn import Block
        if not isinstance(blocks, list) or len(blocks) > 100 or len(json.dumps(blocks).encode()) > 512_000:
            raise ValueError("输出块超过 100 项或 512 KB")
        validated = [Block.model_validate(b).model_dump() for b in blocks]
        sender, transfer = turn["sender"], turn["id"]
        root = self.root(sender, transfer)
        outputs = []
        for value in paths:
            path = Path(value)
            if not path.is_absolute() or path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("只允许登记当前任务目录内的文件")
            if path.stat().st_size == 0:
                raise ValueError("输出文件为空")
            with path.open("rb") as stream:
                content_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            outputs.append({"path": str(path), "hash": content_hash})
        saved = self.ctx.state.get(self.key(sender, transfer), {})
        saved.update(outputs=outputs, result_blocks=validated)
        self.ctx.state.set(self.key(sender, transfer), saved)
        return {"success": True, "files": [{"number": i + 1, "name": Path(f["path"]).name} for i, f in enumerate(outputs)], "message": "输出已登记，等待用户明确选择回传附件"}

    def finalize(self, response_text="", **kw):
        turn = self.turns.get(str(kw.get("session_id") or ""), {})
        if not turn or kw.get("turn_id") != turn.get("turn_id"):
            return None
        if turn.get("reply") is not None:
            self.deliver_card(turn)
            return turn["reply"]
        if not turn.get("command_result"):
            return "QuanSyn 指令未取得实际执行回执，请重试。"
        if turn.get("executing") and response_text:
            key = self.key(turn["sender"], turn["id"])
            saved = self.ctx.state.get(key, {})
            saved.update(result=response_text, completed=True)
            self.ctx.state.set(key, saved)
            self.deliver_card(turn)
            outputs = saved.get("outputs", [])
            files = "\n".join(f'{i + 1}. {Path(f["path"]).name}' for i, f in enumerate(outputs))
            return response_text + f'\n\nQuanSyn 回传：发送“推送 QuanSyn {turn["id"]}”。' + ("\n可选附件：\n" + files + "\n回传附件时在指令后加“附件 1,2”。" if files else "")
        return None
