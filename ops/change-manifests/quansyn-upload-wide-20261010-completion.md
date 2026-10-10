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
remaining_risks: 文件大小不设固定限制，但受磁盘空间及网络约束；文档解析/模型处理能力与原件传输是不同能力，既有执行限制本轮未更改；iOS构建86Apple上传仍受TLS阻断

## 架构与盘点

开工盘点见ops/acceptance/quansyn-upload-wide-20261010/git-inventory.json。遵循用户直接提供的一任务一分支一Worktree指令，高于仓库旧main-only规则。原任务、main及其他worktree无改动。
复用现有QuanSyn POST /files、私有artifact存储与同一身份隔离，不引入第二存储/服务/依赖。_save兼容原bytes调用且支持BinaryIO分块落盘；下载完整性校验改为分块，不降低SHA256要求。空文件、幂等冲突、清理、归属仍检查。
前端复用upload及原composer，粘贴仅消费图片事件，普通文字保持原生粘贴；混合图片文字保留文字。草稿缩略图使用本地Blob URL，移除/发送/退出/卸载释放。上传和下载取消短固定客户端超时，其他请求维持现有超时。原设计CSS保留，仅追加>=1600px宽屏覆盖。
代理仅QuanSyn原件上传路径设置client_max_body_size 0与关闭请求缓存，保留其他接口上限。

## 变更文件

backend/api/quansyn.py、backend/services/generated_artifacts.py、frontend/Dockerfile、frontend/src/features/quansyn/{QuanSynDesign.jsx,QuanSynPage.jsx,quansyn.css}、frontend/src/services/platformApi.js；扩展现有前后端测试及本任务证据。

## 本地验收

后端14 passed；前端155 passed，0 failed；生产构建成功；py_compile与git diff --check通过。真实大附件测试超过50MiB，Web API上传→传递记录→鉴权下载的SHA256一致。共享存储验证有界读、幂等返回、内容篡改拒绝、空流拒绝及临时目录清理。
