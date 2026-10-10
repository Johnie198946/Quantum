# QuanSyn 上传、图片粘贴与宽屏适配

task_id: quansyn-upload-wide-20261010
status: TESTED
branch: codex/quansyn-upload-wide-20261010
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quansyn-upload-wide-20261010
head/local_commit: 开工基线5f8a83f9da4a73a2379b21029dc27cc8f4ce040c；本轮尚未提交
remote_sha: 本轮未推送
server_before: 048c66363f08189674453473958e8d921ad7ac25（生产.deployed-sha只读）
server_after: 未部署
health_check: 本地后端14测试、前端155测试及构建通过
functional_check: 真实61MiB级附件上传、落库引用、下载SHA256一致；图片粘贴handler测试通过，生产浏览器粘贴及宽屏待验证
rollback_point: 尚未部署，无新增外部变更
manifest: ops/change-manifests/quansyn-upload-wide-20261010-completion.md
remaining_risks: 文件大小不设固定限制，但受磁盘空间及网络约束；文档解析/模型处理能力与原件传输是不同能力，既有执行限制本轮未更改；iOS构建86由用户切换网络后手动上传，Apple页面已显示正在处理；尚未核对TestFlight可安装

## 架构与盘点

开工盘点见ops/acceptance/quansyn-upload-wide-20261010/git-inventory.json。遵循用户直接提供的一任务一分支一Worktree指令，高于仓库旧main-only规则。原任务、main及其他worktree无改动。
复用现有QuanSyn POST /files、私有artifact存储与同一身份隔离，不引入第二存储/服务/依赖。_save兼容原bytes调用且支持BinaryIO分块落盘；下载完整性校验改为分块，不降低SHA256要求。空文件、幂等冲突、清理、归属仍检查。
前端复用upload及原composer，粘贴仅消费图片事件，普通文字保持原生粘贴；混合图片文字保留文字。草稿缩略图使用本地Blob URL，移除/发送/退出/卸载释放。上传和下载取消短固定客户端超时，其他请求维持现有超时。原设计CSS保留，仅追加>=1600px宽屏覆盖。
代理仅QuanSyn原件上传路径设置client_max_body_size 0与关闭请求缓存，保留其他接口上限。

## 变更文件

backend/api/quansyn.py、backend/services/generated_artifacts.py、frontend/Dockerfile、frontend/src/features/quansyn/{QuanSynDesign.jsx,QuanSynPage.jsx,quansyn.css}、frontend/src/services/platformApi.js；扩展现有前后端测试及本任务证据。

## 本地验收

后端14 passed；前端155 passed，0 failed；生产构建成功；py_compile与git diff --check通过。真实大附件测试超过50MiB，Web API上传→传递记录→鉴权下载的SHA256一致。共享存储验证有界读、幂等返回、内容篡改拒绝、空流拒绝及临时目录清理。

部署环境检查：API /tmp为256MiB tmpfs，上传TemporaryFile改为现有owner私有持久附件目录，并补充测试强制验证临时目录选择；14项后端测试重新通过。第一轮正式脚本执行被本任务中止并触发既有回滚，等待旧release恢复后继续；不绕过部署锁、活动任务、镜像及存储权限检查。

## 临时中转清理（用户追加要求）

现有 /imported 是唯一清理入口：客户端确认资料已持久保存后，删除该需求 text/blocks/files，并删除无其他传递引用的 quansyn_file 私有目录（含原件与 receipt）；保留编号、摘要、状态供幂等重试及结果关联。复用 TenantMapping 行锁，串行化同账号的提交、附件保存与清理，避免共享引用检查与新增引用并发。普通生成附件不删除；回传结果不自动清理，供网页复制下载。没有迁移/回填删除旧历史。

提交重试先查原 request_id/digest，再验证附件，已清理的附件不会破坏相同提交重试。领取同 claim 的已导入记录可重试确认，iOS 使用既有持久草稿分支；Mac 补充服务端确认响应丢失的恢复路径，保留本地正文与附件。

后端/真实DB/Mac插件/私有文件共22项通过；前端155项通过、生产构建通过。覆盖下载后未确认不删、错误claim不删、成功清理、共享待领取保留、最后引用清理、清理IO失败回滚与重试、已删除附件提交重试、结果回传、Mac实际API确认响应丢失恢复。本地SQLite测试不验证Postgres行锁并发调度，生产健康及浏览器功能待完成。

先前中止部署的回滚已核对：生产marker仍048c66363f08189674453473958e8d921ad7ac25，API/front运行image与开工一致；旧API localhost /api/health 返回404（错误检查路径，不作健康成功证据）。回滚点 /opt/ai-lab-shared/rollbacks/quansyn-upload-wide-20261010.axrZwG。
