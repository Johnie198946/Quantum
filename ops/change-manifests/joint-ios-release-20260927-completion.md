# 联合 iOS 发布验收

task_id: joint-ios-release-20260927
status: COMMITTED（运行代码已提交，尚未推送此联合候选）

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
