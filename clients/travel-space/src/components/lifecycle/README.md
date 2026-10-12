# 旅行全生命周期接入设计

本目录是独立旅行设计 worktree 的本地界面与领域适配交付。canonical 产品工作区、服务器、数据库与其他任务改动保持原样。不能据此声称后端已部署、Siri 已安装或设备已授予录音权限。

最新 backend/iOS 合同判断来自已用 `git ls-remote` 核对的 main `de3c2ad00a4fb33029d7138f52622689be3267e7`，同时记录了落后 64 提交且有既有改动的 canonical checkout。详细证据、真实路由和源码 SHA256 见 [lifecycle-backend-audit.json](../../../../lifecycle-backend-audit.json) 与 [lifecycle-backend-audit.md](../../../../lifecycle-backend-audit.md)。

## 本地状态边界

`profile.tripSession` 保存出发/结束时间、出发时计划快照、实际事项事实、事件、回顾和核对状态。游前/游中/游后页面切换只是浏览导航；只有明确出发/结束动作改变旅行状态。

以下集合独立保存，并通过稳定 ID 关联：

| 集合 | 所有者与用途 |
| --- | --- |
| `days[].items[].journalId`、`journalRevisions` | 计划事项、安排变更与差异对照 |
| `profile.tripSession.facts`、`events` | 用户确认的实际开始/完成/跳过等事实 |
| `profile.journalRecords` | 用户原话、照片、录音与片段 UUID |
| `profile.budgetLedger` | 已付/预计账目、成员、原币/汇率快照、实际转账记录 |
| `profile.tripSession.recap` | 用户自己的总结，不被重新生成的计划覆盖 |
| `profile.tripSession.checks` | 最后回顾已核对的时间与本地来源签名，不等同旅行结束或资金结清 |

AI 建议只生成待确认的计划或文字草稿，不提交实际进度、不把预计账目变成已支付，不覆盖原话、付款快照或回顾。现有旅行重排 validator 对旧 `journal` 与 `illustrations` 做强保留；`extra=allow` 不会自动保护新加的 ledger/fragments/participants 字段。因此新领域集合不能仅依赖 AI 返回整个旅行 JSON 来保存。

## 复用已实现合同

| 交互 | 真实已有合同 | 接入约束 |
| --- | --- | --- |
| 查资料、完善偏好、生成行程 | `workflow.create`，`output_kind=travel`；`POST /api/v1/capabilities/proposals` / `confirm` | 继承本轮目的地、日期、同行与偏好；未知保持空；来源查询失败保留 `open_questions`。 |
| 阅读安排及资料依据 | workflow execution / artifacts / artifact content | 校验实际 artifact hash；旅行 v2 包含稳定 action/stop/source ID 与来源核验时间。 |
| 记录实际进度 | `POST /api/v1/workflow-executions/{execution_id}/travel-revisions` | 当前 completed execution、最新 artifact ID/hash、固定 request UUID；实际时间带时区且不得在未来；终态不可覆盖。 |
| 用户确认修改未来安排 | 同上，提交 `proposed` 而非 `progress` | 每次只修改计划或进度之一；按已有服务端规则冻结历史/锁定事项/真实预订；显示差异后确认。 |
| 让 AI 重查、重排剩余行程 | `POST /api/v1/workflow-executions/{execution_id}/request-revision` | 绑定最新旅行 artifact/hash 与 `travel_research` 或 `travel_itinerary` 节点；不可把 DSL plan PATCH 当旅游事项编辑。 |
| 私人手记、记录原文 | `PUT /api/v1/me/knowledge-notes/{note_id}`、知识 note create/update | 完整 Markdown、SHA256；主动提供 `base_hash`，版本冲突时拉取或保留副本；笔记保存时快照与最新安排分开。 |
| 拍照/导入/录音/分享 | 现有 client action capability 与 receipt | 遵循设备用户触发、权限、取消与成功/失败回执，绑定认证用户。 |
| 音频变文字 | `voice.transcribe`、`POST /api/v1/documents/voice/transcriptions` | 真实 transcript 才能进入草稿；缺服务/空转写明确失败；不能使用 SpeechRecognizerService 的演示转写作为购物内容。 |
| 保存游后 PDF/表格 | `office.pdf.create`、`office.spreadsheet.create` | 输入用户确认过的真实事实/账目快照；文件 receipt/hash 不能替代金额账本的验证。 |

现有 iOS `WorkflowDashboardView` 已有 private durable travel cache/pending queue，按作用域保存，基于当前云端安排重放、固定 request UUID、成功回读后出队。后续原生接入应复用这条通路。HTML 原型中的本地事件不代表已经调用服务器。

## 需要新增的合同（设计建议，尚未实现的 API）

金额账本需有支出 UUID、原金额/币种、已采用汇率及来源/时间、结算币种、支付成员与金额、承担成员与金额、预计/已付状态、关联 action/source、修订号及退款/更正记录。单笔换算一次后分配到每人，保留尾差，总付款和总分摊必须等于该笔总额。平分按结算币种最小单位分配，避免一日元跨币种拆分后产生偏差。

转账回执单独保存，不重复计作费用。用户在支付应用完成转账后登记，可登记部分金额；界面建议转账方案不代表执行了付款。共同记账还需要真实认证的 trip membership/invitation/roles；当前分账姓名和 `companions` 人数不能充当共享授权。

亲历碎片需有 UUID、day/action/stop 可选关系、实际时刻/时区、用户原话、私有媒体引用/hash，以及从原话派生的整理版来源。原话始终保留。暂时没有地点或时间时明确未知，不用示例地点补齐。

游后总结以实际完成/跳过/取消状态、原片段与行程修改记录为事实基础；已付账与预计费用分开。最终回顾/结算快照需要绑定这些集合的版本和 hash，能够重现导出。当来源变化时保留原总结，并提示用户重新核对。

新合同应注册 PCM schema、owner/成员策略、确认、幂等和回执，再接入持久化；本设计没有宣称任何新 expense/member/settlement API 已存在。

## TripReview 界面与调用

```jsx
<TripReview
  onBudget={tab => openExistingBudget(tab)}
  onRecord={dayId => openExistingDayRecords(dayId)}
  onBackToToday={() => showToday()}
/>
```

组件使用 `useTravel()`、`normalizeSession`、`summaryFacts` 和 `statusOf`。费用/分账完全复用现有 `normalizeLedger` / `ledgerEntries` / `summarizeLedger` / `formatMoney`；点击费用或分账转入同一个 `BudgetPanel`，没有第二套计算器或付款界面。

版面依次为实际记录小结、用户总结、出发计划与实际对照、原话/照片/录音、已支付汇总及待核对事项、最后回顾确认。复用玻璃卡片、浮动标题输入、弹簧动效、Disclosure 和确认按钮。减少动态效果设置生效。

`recap` 保存 `{text,updatedAt,factsFingerprint}`；`checks` 保存 `{reviewedAt,reviewedFingerprint}`。本地签名只提示来源变化，不是安全 hash 或服务器 CAS。总结按钮按已存在的事实起草，没有真实 AI 服务调用。实际结束旅行之后才可确认最终回顾；确认保留待核对费用和分账，不暗中支付、转账或清空记录。

## 一句话购物记账与 iOS

本任务已有 `native-budget/` 源码交付可用于 Swift Decimal、用户触发的 Speech 和 Siri AppIntent 草稿队列。它未集成到 canonical iOS host；HTML 中只有识别到真实 WK bridge 时才调用原生能力。拿起手机不会自动打开后台麦克风。实际 Siri 短语/快捷指令或记账按钮是用户触发入口。

确认链路：真实转写或用户文本 → 购物草稿 → 补齐金额/币种/付款人/日期 → 用户确认 → 稳定 UUID 本地保存 → 后续持久化域/同步确认。缺失或含歧义的金额不静默入账；快捷指令 draft 读取不提前从队列删除，保存后按 source UUID 去重。详见 [native-budget/README.md](../../../native-budget/README.md)。
