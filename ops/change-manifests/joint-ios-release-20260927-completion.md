# 联合 iOS 发布验收

task_id: joint-ios-release-20260927
status: DEPLOYED（b9e4d128已部署且健康通过；笔记真实模型语义/性能验收尚未通过）

## 范围与证据

联合笔记/阅读/旅行/图片与导出修复。运行代码候选543d328179ad40303bf1b02bd13220a46ec04ad7；本提交仅新增交付记录，不更改已测代码。196项客户端回归通过于6a935b01；后续图片扩展名修复有单项Swift回归通过。133项联合后端回归通过、1既有跳过；阅读5项UI通过。其他旅行/图片完整矩阵详见各自manifest。

最终543真机：用户协助PhotosPicker选择应用截图，随后Chat请求16:9 JPG、提案确认、工作流澄清/规划/启动、本机像素处理、结果审核、预览、系统JPEG分享均执行。独立下载HTTP200，1200x675 JPEG，sha256 4d40672c511717eabac0e2a32cb6ef026bbd0f0a3113fdd0834c972e1a517af4，workflow completed，source_kind ios_native。隔离后端6a与543后端字节相同。证据/tmp/quantum-image-final-ui/result.json。系统分享截图含联系人建议，仅本地，不提交。

## Git 盘点

- branch: codex/knowledge-ui-refresh-20260927
- worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/knowledge-ui-refresh-20260927
- 开工status: 干净；HEAD 543d328179ad40303bf1b02bd13220a46ec04ad7。
- remote origin: https://github.com/Johnie198946/Quantum.git；source: https://github.com/Johnie198946/ai-lab-platform.git。
- git ls-remote origin refs/heads/main: 167fba5c956ade6daba6568fc70c35d7f679406b。
- 既有canonical main位于/Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0，21250c7且包含其他任务脏修改，未覆盖；旅行worktree仅独立收据提交。原阅读任务明确冻结移交本联合候选，由本任务继续集成。

## 发布边界

server_before: d228c06d6865bdbca9329f264acfe4cf0e8fc5f7
server_after: 尚未执行本轮联合部署
health_check: 尚未执行本轮联合部署检查
functional_check: 隔离真机图片全流程通过（选图有用户协助）；生产笔记语义/耗时复测未通过，等待额度授权
rollback_point: 本轮未建立，部署前建立；现有生产回滚见chat-travel-pcm-d228c06d6865

## 未完成项

- TestFlight未上传；旧Build70归档仅a8cc客户端，不用于本联合版本。最终构建号尚待统一。
- 笔记全量语义/耗时复测等待临时15m额度明确答复；当前12m配置未恢复，账本未改。
- 旅行部分SLO目标及完整端上弱网/大附件矩阵未全部通过，不将成功率当性能达标。
- 生产新刊UI验收由出版任务在图片恢复生产会话后执行；部署须协调短窗口，不能打断验收。

## 联合归档准备

7b65187aac2cf34a6eda7a4265562e42507b7495已推origin/main并独立ls-remote一致。运行代码仍543。统一构建号72（71曾用于本地验收，70旧归档不分发），仅更新project.yml/pbxproj两处版本定义；Apple可用性尚待validate。设备已恢复生产70并交出版新刊UI验收。后端仍d228。

## Build72归档结果

归档source=e52d8a9f21bf33e56c2ef35652d071f656b0028b，路径/private/tmp/Quantumn-1.0.3-72-e52d8a9f.xcarchive，Release ARCHIVE SUCCEEDED。版本1.0.3(72)，194个源文件与提交逐字节一致。codesign沙箱初次返回CSSMERR_TP_NOT_TRUSTED，在系统信任访问环境独立重试exit0通过。证据/private/tmp/note72-artifact-verification.json与note72-final-archive.log。Apple validate尚未执行，未上传。

图片manifest顶部已同步当前已推/真机UI通过状态（明确用户协助选图），不再让旧历史状态覆盖最终结果。本次后续文档提交与e52运行代码完全一致。

## Apple校验

Xcode实际显示“AIPlatformApp 1.0.3 (72) validated / Your app successfully passed all validation checks.”，截图/private/tmp/build72-validation-passed.png。Apple校验通过，不等于TestFlight上传；尚未执行Distribute/Upload。共同main已核b9e4d128dd5839bae89cff39790fb8240297e23e，生产联合部署正在旅行任务执行，未把进行中写成已完成。

## 上传状态更正（21:21现场复核）

Xcode实际窗口现显示App upload complete / AIPlatformApp 1.0.3 (72) uploaded；ContentDelivery.log证明2026-09-27 21:19:03 UPLOAD SUCCEEDED with no errors。build_id=0e03ed6f-0bde-4ba1-88c5-aa45abb7429c；摘要/private/tmp/build72-upload-receipt.json。先前“未上传”的记录已过时。本次恢复上下文后未操作上传按钮，不能据此确定由哪个UI操作触发；笔记语义验收门禁未完成而上传已经发生，明确记录顺序偏差，不将上传作为验收通过。Apple后续处理/测试组可用性待核实。

## b9 联合生产部署与独立核验

- head/local_commit与remote_sha: b9e4d128dd5839bae89cff39790fb8240297e23e；git ls-remote origin refs/heads/main 独立核对一致。
- server_before: d228c06d6865bdbca9329f264acfe4cf0e8fc5f7。
- server_after: b9e4d128dd5839bae89cff39790fb8240297e23e，/opt/releases/ai-lab-platform-b9e4d128dd58.gR3lJT。
- health_check: 8容器healthy；API与3worker镜像revision=b9；Bridge/ChatWorker active；内部ready、Bridge health及https://t-react.com/health均HTTP200。
- functional_check: 已出版期唯一、正文/illustration_plan哈希一致076cbb867c99609ea8ff09322ffcdf5f391990a6df7960c7f708f6776d5c5c9f；笔记/图片接口验收继续，笔记语义/耗时未验收。
- rollback_point: /opt/releases/ai-lab-platform-d228c06d6865.CbxC2W；完整备份/opt/ai-lab-shared/rollbacks/chat-travel-pcm-b9e4d128dd58。PG SHA256=12040648ca51849ddbe3f1c8f4ee18009437d6d4a78a34eb95d603fbf824b46e；publication SQLite=863c14f2bea070089baf2930c794ce5fe21dd6fcef184e5786c0fea18be53209；媒体=02e9ea55f8852fff51c02b700decea1fbfba99b40d35846714b9da4dfb619642；三个hash与SQLite integrity均通过。
- API、3worker、Bridge与ChatWorker额度仍12000000，账本未调整。
- Build72上传确认时间21:19:03，回执PROCESSING；尚未核实Apple后续可用状态。发布manifest本段仅本地追加，未为文档再次移动main。

### 生产接口复验

根任务在b9独立执行既有catalog-context-functional.py：136篇完整正文、5页、防跳页通过、正文hash全匹配、模型响应无重复snippet、note_mutations=0；semantic_review_complete=false，接口检查不能替代真实模型语义验收。

部署任务生产功能smoke exit0：图片上传/下载一致、无效图422、跨用户404、doc原件/私有笔记/图片workflow和PCM确认通过；CSV BOM、普通JSON（含envelope键）、TXT、MD真实导入与租户隔离通过。证据/tmp/travel-build72-release/functional.log。此smoke model_calls=0且opt-out共享编译，不代表模型编译验收。publication-before与after全字典相等（正文、bundle和5媒体hash）。出版pin与10cron恢复待独立回执。

### 出版恢复回执

出版任务独立复核server/API b9和ready/healthy通过；读者API10章、3插图锚点/caption/alt/version、5媒体HTTP200/hash一致。10条cron及wrapper已pin b9并恢复原enabled，原prompt/schedule/model未变；active=[]。本机恢复备份publication-joint-b9e4d128。部署保护窗口结束，无遗留暂停。

当前remaining_risks：真实模型笔记语义与耗时尚未通过；临时15m配额问题待明确答复（当前12m，未改账本）；Mac自动锁屏阻挡后续真机与Apple处理状态确认；旅行部分SLO及私人资料矩阵未全通过。Build72上传成功不能当作整体验收通过。manifest最新回执仅本地，git diff --check通过。

部署执行任务最终收据：独立分支codex/travel-notes-20260927提交b2742530ebf81748a22d8c7f8310f509af7c0ad5，执行方已ls-remote核对；共同main未移动。无剩余生产负载。包含完整备份hash、功能检查及出版cron恢复证据；整体继续DEPLOYED，剩余验收条件不变。

## Build73 发布启动（用户明确“发布”）

继续本联合任务隔离branch/worktree，适用用户“一任务一branch/worktree”优先于仓库旧main-only规则。开工HEAD/remote=b9e4d128dd5839bae89cff39790fb8240297e23e，git fetch origin main成功且未分叉；原工作区仅本任务manifest脏。canonical/main旧21250及他人修改不动。

按hunk合入confirmation-fix原5文件（patch SHA256 a1193976c26470db03b0cc5864785d0da4e79be13673a76db11bebbd7edb3a5e）与image-direct 13文件（921cfcd25d920632b20358b21bb3b9cb1d6847c370f3ea4f3ad2f4a7aef463e7）；原任务worktree保持不动。Build72→73，仅两处项目版本值。

组合后端150通过（/tmp/build73-python.log），iOS组合203通过（/tmp/build73-ios-tests.log）；触及Python Ruff、PCM文档及iOS矩阵生成检查通过。新增发现图片cancelled且节点均succeeded时retry 409，由图片任务独立增量修复中，未将当前补丁当作覆盖该问题。当前Build73尚未提交推送部署/上传；原生产b9/Build72不变。

### Build73 最终本地校验

409增量SHA256=92b6292f3af1a622afab3fc98a7ab999b24bfbbdf41baf600cb6010a2e732ed0，扩展现有图片retry及按attempt选择instruction；原远端失败不伪造重试成功。最终组合后端196 passed（/tmp/build73-python-final.log），iOS203 passed且409增量不改客户端；Ruff/生成合同/diff检查通过。Release ARCHIVE SUCCEEDED（/tmp/build73-archive.log），/private/tmp/Quantumn-1.0.3-73.xcarchive签名校验exit0，版本1.0.3(73)，203个iOS跟踪文件与归档开始快照hash完全一致。

本次发布用户已明确授权推送、部署及TestFlight；现在进入提交推送阶段。新版真机全链路仍由图片任务隔离验证，未用模拟器代替真机。笔记全量语义/耗时历史剩余项不列为本轮已修复。
