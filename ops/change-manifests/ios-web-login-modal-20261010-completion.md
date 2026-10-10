# QuanSyn App/Authen 登录及轻量对齐

task_id: ios-web-login-modal-20261010
status: DEPLOYED
branch: codex/ios-web-login-modal-20261010
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/ios-web-login-modal-20261010
head/local_commit: b904a9995016d7bb6932172fee7e28f20cafc7d6（已部署产品代码；证据追记提交另见Git HEAD）
remote_sha: b904a9995016d7bb6932172fee7e28f20cafc7d6；git ls-remote origin refs/heads/codex/ios-web-login-modal-20261010 已核对；origin=https://github.com/Johnie198946/Quantum.git
server_before: fb886d00ba99620da6527f922a97115afda5b63e，/opt/releases/ai-lab-platform-fb886d00ba99.UQZBoj
server_after: b904a9995016d7bb6932172fee7e28f20cafc7d6，/opt/releases/ai-lab-platform-b904a9995016.K1iMD8；API/3worker/frontend镜像revision均匹配
health_check: 八个容器healthy；API ready、Authen health、Hermes Bridge health HTTP200；Bridge与chat-worker active；独立最终检查见server-final.json
functional_check: 正式网站/JS/CSS HTTP200；Authen代理start/status HTTP200/pending；未登录pending401；失效state410；完整真实隔离网页+iOS+Quantum+Authen确认/取消通过；正式账号可见自动跳转仍待用户验收
rollback_point: /opt/ai-lab-shared/rollbacks/quansyn-login-20261010.pmHknK（原release/SHA/5镜像/离线指纹/SQLite快照/Postgres备份）；Authen独立点n0uOAS
manifest: ops/change-manifests/ios-web-login-modal-20261010-completion.md
remaining_risks: 正式账号App确认与网页跳转待验收；87已由用户确认手动上传，Apple处理未独立检查；飞书真实绑定未验收；18:10完整生产回流未执行；18:00知识治理任务仍停用

## 开工盘点和范围

开工时status干净、分支/HEAD/remote/worktree五项原样记录在ops/acceptance/ios-web-login-modal-20261010/git-inventory.json。用户任务隔离规则优先于旧main-only规则。用户已授权提交、推送、部署和完成剩余项目。没有修改其他任务工作区；依次合入服务器08ff1774、c3809542和fb886d00，保留其他任务改动。

产品代码提交77c191e7；最终合并部署提交b904a999。复用external_auth、AuthContext、AppRoot、APIClient、官方Logo和现有capability_handlers/contracts、回流脚本；新iOS视图补足App授权模态框。Authen源repo拥有验证码/授权/一次性票据；Quantum只代理并沿既有流程接入租户。无新服务、表或依赖。变更文件以77c191e7及最终合并提交清单为准，涵盖认证代理、网页/Nginx、iOS/API/弹窗、架构门禁修复、回流脚本、测试与本任务计划证据。

## 验证

198项后端与架构/能力/QuanSyn/配对/同步回归通过；最终fb886合并115项回归通过；网页156项和生产构建通过；Authen32项真实Redis/SQLite测试通过。真实隔离服务与App完整确认、自动登录、取消流程通过，截图ios-authen-success.png。结果详见validation.json及同目录记录。没有生产mock。

构建87 Debug正常签名BUILD SUCCEEDED、Release ARCHIVE SUCCEEDED；现有SignedKeychainAcceptanceTests安全写读删探针1项通过。早期无签名模拟器包导致凭证保存失败、泛化为协议报错；已重新安装正确签名包，可见现有聊天会话恢复。用户确认手动上传87，未重复上传或声称Apple处理完成。

原18:10入口已安装经过SHA核对的回流脚本，失败即停止、冲突隔离；脚本hash=3c97c6dea349feff84759b71ee287209817143759791509bda12bcf8501faa62，runtime54e2与最终代码脚本相同；安装与回滚见native-sync-install.json。QuanSyn处理结果沿中央库即时对齐、临时输入导入成功后ack清理；知识回流仍沿原计划，18:00治理停用未解除。

## 部署与回滚

发布前建立上述完整回滚点，保持部署锁、CAS、磁盘5GiB、离线镜像SHA/revision、运行审计和健康保护。早期发布包目录权限问题触发迁移导入失败并自动回滚；修正包权限后候选导入/静态读取通过。空间不足仅清理本任务未部署的重复产物，未降低磁盘保护或清理业务数据。最后复用刚生成的完整pmHknK回滚点继续同一候选。SSH日志停留在step5，部署锁/进程已不存在；独立最终核对已确认新release、八容器及API/Authen/Bridge健康，见deployment-result.txt/server-final.json。

回滚恢复pmHknK原release链接和5个原镜像/离线指纹，使用原部署工具执行并重做健康/功能检查；数据库快照仅在确有需要且用户授权恢复数据时使用。Authen恢复n0uOAS两Python文件并重启authen@auth。Mac入口恢复~/.hermes/backups/quansyn-sync-20261010原脚本。正式账号完整可见验收尚未完成，因此状态保持DEPLOYED，不宣称全部VERIFIED。
