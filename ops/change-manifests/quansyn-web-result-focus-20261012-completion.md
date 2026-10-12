# QuanSyn Web 结果自动聚焦

task_id: quansyn-web-result-focus-20261012
status: TESTED
branch: main
worktree: /tmp/quansyn-main-migrate-20261012（用户明确授权的隔离干净检出；规范主工作区保持原样）
head/local_commit: pending
remote_sha: pending
server_before: pending
server_after: pending
health_check: pending
functional_check: 生产基线归并后前端 157/157、QuanSyn/Travel 后端 31/31、生产构建通过；当前生产 Travel 提交 a45e269d 已合并，自动聚焦回归通过
rollback_point: pending
manifest: ops/change-manifests/quansyn-web-result-focus-20261012-completion.md
remaining_risks: 部署前须核验远端 main、重建目标 SHA 离线镜像、记录回滚点、检查服务健康及真实登录后的 Web 页面行为

## 变更

- 将既有 QuanSyn 生产代码按原提交作者身份迁移到 GitHub `main`，不修改原本含未归属改动的规范主工作区。
- Web 首次加载或轮询发现新 `result` 记录时，自动切换到该记录对应设备会话。
- 切换设备或收到新消息后，将聊天区域定位到最新气泡；不合并 iOS/Mac 数据，不改变服务端目标、权限或回传协议。
- 增加回归测试：新 Mac 结果触发 `mac`，已见结果不重复抢占用户当前选择。