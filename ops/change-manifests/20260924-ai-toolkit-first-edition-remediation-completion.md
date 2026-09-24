# 首期《AI 工具实战》整改与双封面接入 — 完成清单

- task_id: `20260924-ai-toolkit-first-edition-remediation`
- status: `VERIFIED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/quantum-2.0-publication-main`
- publication runtime implementation SHA: `076cc97a18aa82544f2503e256327883556d5e27`
- production baseline before publication action: `b4a2d34a2d233208b677120f354045ec88b3121c`（`076cc97…` 的后代；两者之间没有 publication runtime 文件变化）

## 生产发行结果

- due-time check: `2026-09-24 12:02:14 CST (+0800)`，已到 `12:00` 发行时点。
- deterministic command: `python3 scripts/publication_release_remote.py --target-publication-id publication-ba63df8c93444d40f9e12c9edf627a0b`，exit `0`；随后独立读取 operator/store，而非仅依赖退出码。
- publication_id: `publication-ba63df8c93444d40f9e12c9edf627a0b`
- edition_id: `edition-d145b9709219ab79a016ed6133eb067d`
- issue_id: `issue-ba63df8c93444d40f9e12c9edf627a0b`
- title: `用 Gemini Notebook 把一份长 PDF 变成可核对的学习笔记`
- state / actual_release_at: `published` / `2026-09-24T04:01:07.564241+00:00`
- body/content SHA-256: `880adb190d6514c35c5b2ed7a34ae0cc16fbd32119b14e556345db7fddaad8a7`
- blocked reasons: `0`
- editorial approval: attempt `attempt-6bf0d62069474ec497d9c51354035944`, revision `4`, state `approved`, open gaps `0`, review SHA-256 `d1f02b26710bb15a1d481f59276e10566672f3ea06a689d4e28c8fe000c1368d`。
- shelf cover: JPEG `1440×2560`, `836721` bytes, SHA-256 `64a08525c04af6a31e0d3403017a5003d3aeec8c9f9183ead9621e09531f6524`。
- reader cover: JPEG `2560×1440`, `682365` bytes, SHA-256 `6872030e353378305ea958d0a3307ad070e5ad3492892faab6bd532a6c9ea241`。
- replaced publication: `publication-9b5b298fb96bd44dfccb04c36fad8134` 在新刊已证明 published 后执行 withdraw；回读 state=`withdrawn`, withdrawn_at=`2026-09-24T04:03:54.857592+00:00`。

## API / 消费验证

- 使用生产中已有且已签署当前协议的真实主体签发短时 JWT，调用真实 HTTP API；没有伪造协议接受记录，也没有输出主体或密钥。
- `GET /api/v1/knowledge-bookshelves`: HTTP `200`；书架仅投影新 publication/edition/title，`shelf_cover_url` 正确；旧标题不再是活动条目。
- `GET /api/v1/knowledge-books/publication-ba63df8c93444d40f9e12c9edf627a0b`: HTTP `200`；title、edition_id 与 `content_version=880adb…` 正确，`reader_cover_url` 正确。
- 两个认证封面端点均 HTTP `200`，字节哈希和尺寸与发行 receipt 一致；无凭证封面请求 HTTP `401`。
- 合成未签约主体正确返回 HTTP `428`；临时 tenant mapping 已删除，未绕过协议门禁。
- Google signed-in UI 按用户选择明确未测试，不构成本次发行阻塞，也不得表述为已测试。

## iOS 验收

- 当前 `main` (`b4a2d34…`) 使用 Xcode `26.1.1` 对 booted `iPhone 17 Pro / iOS 26.1` 构建：`BUILD SUCCEEDED`。
- 安装与启动成功；现有模拟器会话的 API token 返回 `401`，应用停留在启动页。因此未绕过登录，未完成书架 9:16 封面与阅读器 16:9 封面的真实渲染验收。
- 私有截图仅留在 `/tmp`，未提交 Git。

## 测试真相

- final publication-targeted suite：`113 passed, 17 warnings`；命令覆盖 daily publication、reader projection、editorial workflow、subscription/book API、local/remote deterministic release。
- iOS current-main simulator build：`BUILD SUCCEEDED`。
- 独立保留 2026-09-24 全量结果：`2386 passed, 38 failed, 99 errors, 30 skipped`。失败/错误为广泛既有环境与共享状态问题；不得表述为全量通过。

## Research deposit

- capability: `research_deposit`
- item_id: `item:eda3e02e49e6680cce80a988fd46abfb76a40c2d2eeb9227e805ca5116a27d00`
- source_revision: `91c21864f970cb75ca27e7473f7780835524a60b11d182912ec0c70cfc46cbca`
- receipt SHA-256: `3621409ab2c685d290d46f917251739a1d62198d1ca462ac382e7ed6eb72677a`
- saved/storage_verified/admission: `true / true / admitted`
- queued: `true`，Writer job `c067f0237f86`。
- compiled: `true`；状态回读 `stage=compiled`, `compilation.verified=true`, `wiki_compiled=true`，目标 `wiki/方法论/Wiki Compile Log.md`，event `68fd038159a2ee0270eb8746ecd92c6fd6498204e58b5086abb943f2bb783ba7`。

## 部署与回滚

- server_before publication action: `/opt/releases/ai-lab-platform-b4a2d34a2d23.3ohPyx`, marker `b4a2d34a2d233208b677120f354045ec88b3121c`。
- health before receipt commit: API `/health=ok/0.8.0`, `/ready=ready/0.8.0`; Hermes Bridge systemd=`active`; 8 Compose services均 `running/healthy`。
- rollback_point: `/opt/releases/ai-lab-platform-b4a2d34a2d23.3ohPyx`（完成回执 commit 部署前）；上一实现回滚点 `/opt/releases/ai-lab-platform-076cc97a18aa.P6wnzY`。
- 本文件为 ops/docs-only 回执，不修改 Docker COPY 输入或运行源码。receipt commit 的精确 GitHub/production SHA 与 metadata-only image attestation 由该 commit 的发布后外部收据记录，避免 manifest 自指 SHA 循环。

## 状态字段

```text
task_id: 20260924-ai-toolkit-first-edition-remediation
status: VERIFIED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantum-2.0-publication-main
head/local_commit: receipt commit containing this manifest
remote_sha: receipt commit, verified by git ls-remote
server_before: /opt/releases/ai-lab-platform-b4a2d34a2d23.3ohPyx
server_after: exact receipt commit release, verified externally
health_check: API ok/ready; Bridge active; Compose running/healthy
functional_check: publication/store/API/cover hashes verified; iOS build passed, rendered-cover UI blocked by expired login
rollback_point: /opt/releases/ai-lab-platform-b4a2d34a2d23.3ohPyx
manifest: ops/change-manifests/20260924-ai-toolkit-first-edition-remediation-completion.md
remaining_risks: iOS authenticated rendered-cover acceptance remains unverified; Google signed-in UI intentionally untested; full repository suite remains red (38 failed, 99 errors)
```
