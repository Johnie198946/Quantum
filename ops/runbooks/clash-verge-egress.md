# Mac Clash 反向 SSH 应急出口

## 定位

此链路仅用于服务器本地 mihomo 故障时的**人工应急回退**，不是生产默认出口。生产 Hermes Bridge/Worker 必须默认使用服务器 `127.0.0.1:7890`。

Mac Clash Verge 监听 `127.0.0.1:7897`；LaunchAgent `com.quantumn.clash-egress-tunnel` 可建立 SSH 反向转发，使云服务器 `127.0.0.1:17897` 临时转发至该端口。两个端口刻意分离，避免覆盖服务器本地 mihomo。

## 生产默认状态

```bash
# 服务器
systemctl is-active mihomo.service
ss -lntp | grep '127.0.0.1:7890'
curl --proxy http://127.0.0.1:7890 --fail --max-time 20 https://chatgpt.com/cdn-cgi/trace
```

`/etc/ai-lab-platform/hermes-egress.env` 必须是：

```dotenv
HTTPS_PROXY=http://127.0.0.1:7890
HTTP_PROXY=http://127.0.0.1:7890
NO_PROXY=localhost,127.0.0.1,<bridge-address>,::1
```

## 应急回退

仅当服务器本地 mihomo 已确认故障、短期无法修复且 Mac 隧道已验证可用时：

1. 确认 durable chat 队列不存在 `queued`、`accepted` 或 `running` 任务。
2. Mac 执行 `launchctl print gui/$(id -u)/com.quantumn.clash-egress-tunnel`。
3. 服务器确认 `127.0.0.1:17897` 监听，并经该端口真实访问模型上游。
4. 备份 `/etc/ai-lab-platform/hermes-egress.env`，临时把两个代理值改为 `http://127.0.0.1:17897`。
5. 重启 Bridge/Worker，执行 `API → Bridge → Worker → Provider` 合成请求。
6. 记录故障、切换时间、验证 run ID 与回滚路径。

注意：当前 `scripts/update.sh` 的正式部署契约只接受 `127.0.0.1:7890`。应急值会使正常部署门禁失败，以防临时回退长期化。

## 恢复主出口

1. 修复并验证服务器 `mihomo.service` 与 `127.0.0.1:7890`。
2. 再次确认 durable 队列为空。
3. 将 `/etc/ai-lab-platform/hermes-egress.env` 恢复为 `127.0.0.1:7890`。
4. 重启 Bridge/Worker，并以完整合成请求验收。
5. 确认 Worker 主进程环境指向 `7890`，公网健康接口为 `200`。

切勿仅凭端口监听、systemd `active` 或 `/health` 判断模型链路恢复。
