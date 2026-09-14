# 20260915 iOS 未提交修改返工完成记录

- task_id: `20260915-ios-uncommitted-rework`
- status: `LOCAL_ONLY`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-ios-document-ppt-final-20260912`
- head/local_commit: `fec23ad9205f1ba4cfa9e96507e1cc01151e0c99`（未提交）
- remote_sha: 未重新获取；环境拒绝写入 `.git/FETCH_HEAD`。本地 `origin/main` 为 `fec23ad9205f1ba4cfa9e96507e1cc01151e0c99`。
- server_before: 未检查（未授权部署）
- server_after: 未部署
- health_check: 未执行
- functional_check: iOS Simulator 定向验收 5/5 通过（4 个单元契约测试 + 1 个键盘 UI 测试）；远端完整 PPT 工作流仍未通过。
- rollback_point: 当前 HEAD `fec23ad9205f1ba4cfa9e96507e1cc01151e0c99`

## 盘点与变更

- 删除当前 diff 中的 `HermesReviewComponent` 及伪“保存修改”入口，保留工作流现有反馈/退回链路。
- 统一通过 `AppState.openWorkflow` 切换任务页；Dashboard 首次挂载消费 pending 请求，失败时保留 pending。
- 复用 `WorkflowExecutionView`、`WorkflowArtifactPreview`、`RendererRegistry/QCP`，为现有工件预览按钮补充稳定可访问标识。
- Agent 描述固定包含“功能/适合/边界”，总长不超过 100 字；仅实际生成折叠文本时显示展开按钮。
- 删除当前 diff 中基于焦点的固定底部 padding，继续使用 `ChatView.safeAreaInset` 与系统键盘安全区。
- 增加首次跳转、失败保留、描述边界、QCP 预览契约与键盘可点击回归。

## 验证

- `git diff --check`：通过。
- `xcodebuild ... build`：`BUILD SUCCEEDED`。
- `xcodebuild ... build-for-testing`：`TEST BUILD SUCCEEDED`，应用、单元测试和 UI 测试目标均编译成功。
- 定向单元/UI 测试：iOS 26.0 Simulator 上实际执行 5/5 通过：首次跳转消费、失败保留 pending、Agent 描述边界、QCP 预览入口契约、键盘弹出后发送按钮可点击。

## 未触碰内容与剩余风险

- 两份既有未跟踪交接文档未修改、未删除、未暂存。
- 未提交、未推送、未部署。
- 剩余风险：尚未用全新请求在真实远端链路复验“自动跳转 → 执行中确认/预览 → 最终 PPT 产物”；现有模拟器会话只证明旧伊斯坦布尔请求已创建并进入方案可审阅状态。
