# QuanSyn 上传、图片粘贴与宽屏适配

task_id: quansyn-upload-wide-20261010
status: DEPLOYED
branch: codex/quansyn-upload-wide-20261010
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/quansyn-upload-wide-20261010
head/local_commit: 产品7ad107327e4bfbef8ac95e1ec1b558be8c973500；后续仅验收记录提交单列
remote_sha: origin refs/heads/codex/quansyn-upload-wide-20261010 = 7ad107327e4bfbef8ac95e1ec1b558be8c973500（产品发布前 git ls-remote 核对通过；后续记录提交不改产品源码）
server_before: 2290e35e331de927d57449043fff9ba444f980a3（本轮外层限宽修正）
server_after: 7ad107327e4bfbef8ac95e1ec1b558be8c973500；/opt/releases/ai-lab-platform-7ad107327e4b.o1FLGE
health_check: 五项服务running/healthy；生产 /health HTTP200 status=ok version=0.8.0；nginx -t通过
functional_check: 前端155项通过、构建通过；生产HTML/主脚本/CSS与构建SHA256一致且入口引用新CSS；登录后的27寸工作区/抽屉视觉未核验，原验收窗口已不在Chrome窗口列表中。此前业务测试边界详见下文
rollback_point: /opt/ai-lab-shared/rollbacks/quansyn-workspace-width-20261010.7PbxeL（旧release、5服务镜像、attestation、SQLite/Postgres备份，文件存在核对通过）
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


## Mac 部署与最后补充检查

Mac 只替换用户私有已安装插件 quansyn.py，先断言安装前 SHA256 为9db4a8abcd90ada6c39b617d0444e3611c70f4799f15ac23f3bb124d499507c2，与原安装记录相同。旧模块保存于 ops/acceptance/quansyn-upload-wide-20261010/mac-quansyn-before.py；不修改配置、凭证、其他模块。原生 hermes gateway restart 通过，升级后的 launchd PID3509（此前14559），native status 检查通过。新模块SHA256及备份路径见mac-plugin-update.json。

补充覆盖确认请求到达前中断和响应返回前中断：23项后端/Mac/artifact测试通过；新增单独“非QuanSyn生成原件不得删除”测试1项通过，见nontemporary-test.txt，合计24项。前端155项、构建通过。

浏览器验收仍受 Mac 锁屏阻止（cua getApp 返回locked），已通过异步问题请求解锁；没有绕过锁屏或读取会话凭证。生产公开 /health 返回200 status=ok version=0.8.0。此健康响应尚不能替代新部署后的业务检查。

清理适用于本次部署后成功确认的需求，没有自动扫除历史已导入记录，也不改写已有备份。回传结果保留供用户消费；Web原件暂存取消固定上限，Mac和iOS执行器仍有既有处理限制，未声称任意文件都可解析。


## 最终服务器部署记录

发布脚本退出0，deployment_finished=true。server_before=048c66363f08189674453473958e8d921ad7ac25；server_after=2290e35e331de927d57449043fff9ba444f980a3；release=/opt/releases/ai-lab-platform-2290e35e331d.svh2EG。API与三worker运行sha256:173ef6b8790c2d3345b94d7df6e8a9c5a906e5d09da0fe728ff6e56f9537a3d5；frontend运行sha256:90c6ccf1379e4304c801d6eeed05232c95f1254f14e3a28c2c574ced26e2ff63；五项服务全部running/healthy。实际运行两项后端文件SHA256与测试源码一致，nginx -t通过，公共/health HTTP200。

rollback_point=/opt/ai-lab-shared/rollbacks/quansyn-upload-wide-20261010.VbWNVP，Postgres备份与镜像记录存在；旧release=/opt/releases/ai-lab-platform-048c66363f08.tekuwx。回滚沿用scripts/update.sh门禁并恢复该点镜像/attestation和旧release；数据库为additive migration，不能擅自将整库旧备份覆盖当前业务写入。Mac单模块回滚需核对安装SHA、恢复mac-quansyn-before.py并原生重启。

GitHub发布前和发布后ls-remote两次核对：origin refs/heads/codex/quansyn-upload-wide-20261010=2290e35e331de927d57449043fff9ba444f980a3。随后只提交验收资料、方案文档和1项补充回归测试，产品源码与部署SHA相同。

用户已解锁Mac。Chrome刷新时服务切换期间显示Bad Gateway，恢复后回到登录页，当前无法执行认证后的业务UI操作；异步请求用户在原验收窗口自行填写短信并登录，尚未收到完成回复。没有读取验证码/浏览器令牌。虽然本地真实DB/插件/文件测试和部署文件健康都通过，生产浏览器真实大文件、图片粘贴、宽屏传递页及真实App导入清理仍待验收，因此状态严格为DEPLOYED，未声明VERIFIED或全流程验收完成。


## 27寸照片反馈：外层限宽修正

用户照片与共享 index.css 的 .workspace width:min(1440px,calc(100% - 48px)) / margin:0 auto / padding:24px 0 命中。上一轮内部宽屏覆盖未取消此外层规则，导致宽屏左右空白且 absolute 抽屉从居中容器起点出现。复用原 QuanSyn 工作区、抽屉及动态缩放，仅新增 .quansyn .workspace 的 width:100%、max-width:none、margin:0、padding:0、gap:0 覆盖；不改 Quantum 的共享布局，不新增架构或依赖。

本轮开工 HEAD=2df0c87ba37d72a3222dcda154d1e3a01f7d2305，原任务工作区除既有 frontend/node_modules 依赖链接外干净；完整盘点见 workspace-width-inventory.json。前端155项测试通过，重新构建成功，dist/QuanSynPage-CTkmdQIF.css 确认含外层重置；git diff --check通过。修正当前状态 TESTED，生产仍为2290e35e331de927d57449043fff9ba444f980a3，API/frontend healthy。待提交、远端核对和部署；生产登录后的布局待用户正常登录验收窗口，未读取凭证。

## 外层限宽修正部署结果

产品 commit 7ad107327e4bfbef8ac95e1ec1b558be8c973500 已推送并经 ls-remote 核对。第一轮复用旧后端标记，被原部署门禁 backend image revision mismatch 拒绝，生产指针仍停留2290；未绕过门禁。第二轮基于原镜像仅更新版本标签，RootFS.Layers核验完全相同；没有更改后端代码、依赖或运行参数。五项服务按既有脚本完成部署，脚本退出0、deployment_finished=true。

server_before=2290e35e331de927d57449043fff9ba444f980a3；server_after=7ad107327e4bfbef8ac95e1ec1b558be8c973500；release=/opt/releases/ai-lab-platform-7ad107327e4b.o1FLGE。回滚点=/opt/ai-lab-shared/rollbacks/quansyn-workspace-width-20261010.7PbxeL；旧release=/opt/releases/ai-lab-platform-2290e35e331d.svh2EG。沿用原发布门禁恢复旧镜像/attestation/release；禁止将旧数据库备份覆盖后续业务写入。

health_check：五项running/healthy，nginx -t成功，最终公网/health HTTP200。发布过程中曾有旧API不健康及新API启动期间访问超时，最终恢复并核对通过。

functional_check：公开HTML SHA256 ad25480ff3dc1d1400ed73dde41f0fd18e9f8f955a1a9f5d39a17c41695cce24，入口脚本 index-A9BZzv9V.js SHA256 ea233f01820bd96aff29275165b33ed92ce27ad43426db9c72ba179a3c158085，新QuanSynPage-CTkmdQIF.css SHA256 db24098864ffce9889e54045af9465eca9f5c17020f724b1f05c1130e9ae0a4b，均与构建字节一致，入口确实引用新CSS，含 .quansyn .workspace 外层重置。155前端测试通过，生产构建和diff检查通过。未新增镜像实现复刻测试、依赖或测试假数据。

真实27寸屏幕登录后视觉未核验：原QuanSyn验收窗口已不在Chrome窗口菜单中，现有App Store Connect用户窗口未导航或修改。没有提取凭证或绕过登录。因此最高状态严格为DEPLOYED。生产访问链接 https://www.t-react.com/quansyn/?v=7ad10732 用于刷新页面入口；其query仅作为版本刷新提示，缓存的实际JS/CSS采用新的构建内容哈希。

修复复用现有原稿的absolute抽屉与动态缩放；只在QuanSyn范围取消共享workspace的1440px限宽、居中、外层padding/gap。代码边界检查确认部署前后 backend/agency 产品代码不变，frontend 产品差异只有这一条CSS。发布和检查证据位于同目录 workspace-width-* 文件。
