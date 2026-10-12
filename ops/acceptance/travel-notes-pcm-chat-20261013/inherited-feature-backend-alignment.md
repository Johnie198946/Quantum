# 十步业务功能与后端对照（2026-10-13）

task_id: quantum-frontend-rebuild-20261012
status: LOCAL_ONLY

用户确认的顺序为入口 → 右上角 + 悬浮对话 → 景点文件夹 → 完善计划 → 确认旅行计划／交通预订 → 行程制作 → 采用成稿 → 攻略与保存 → 旅行手记 → 这趟旅行。旧工作流页面清退，仅保留并重构照片处理。

本表区分代码连接、隔离测试和真实服务状态。接口路径均相对于 `/api/v1`。本地补齐不表示当前服务器已经具备新行为，也不以页面通过率代替真实旅行成稿验收。

## 每页功能、接口与保存位置

| 页／操作 | 当前连接 | 保存、回执及约束 | 验证与实际边界 |
|---|---|---|---|
| 1 工作流入口／任务库 | GET workflows；当前 owner + source_client_session_id 过滤；native route ready handshake | 只打开当前对话任务；旧的其他任务以新的只读历史页呈现，保留成果导出 | 原生入口、四导航、所有任务状态页通过；没有恢复旧 Dashboard／Topology |
| 2 右上角 +／悬浮对话／需求总结 | authenticated Chat；converge 的 summary/question/ready JSON | 未知日期、人数、预算保留未定；模型 ready 不能自行补条件；明确收敛后才查询景点；不创建或执行工作流 | Chrome/WebKit 从“我要去青森”入口通过；不能把 QA 的上海、五天、两人、8000 元当作用户最终要求 |
| 2 收敛后展示旅行空间卡片 | Chat 的实际公开资料检索；discovery JSON | URL、查询日期、ID 去重与数量边界；未知坐标保留 null；无实拍时标注风景示意 | 卡片在创建工作流之前出现；空资料／检索失败保留真实错误，无演示景点补位 |
| 3 景点文件夹／收集、移除、确认 | 本机受保护草稿；已选名称／来源／核对日期进入 create.description | 未选区域不扩大研究；天数未定时只是临时意向结构，不能当作最终日程 | 文件夹先于完善计划；制作前草稿按账号、对话和任务分开 |
| 4 完善计划／日期、人数、预算、节奏、兴趣、补充说明 | 用户填写的 requirements；可读旅行 description | 选定日期使用真实 ISO 日期，未知日期不补年份；预算保留币种；12000 字超限明确拒绝，保留草稿 | 模型回归覆盖预算、日期、来源与未知值；无本机草稿的旧任务回到条件核对，避免空交通页崩溃 |
| 5 确认旅行计划／服务端澄清 | QCP workflow.create 的 propose/confirm；clarification/respond；QCP workflow.approve | 创建与启动 request ID 持久复用；服务端 round、计划 hash 和 activation revision 绑定确认；响应丢失不能重复造任务 | 本地 API 验证创建重放、跨用户隔离和不同请求体冲突；仍保留后台必要的需求确认 |
| 5 交通与预订／往返、接驳、住食体验 | Chat 查询有来源资料；渠道入口；用户已有订单通过 confirmed_bookings 的 travel-revisions 关联 canonical action | servicePlan 条件和已有凭据进入制作描述；用户改变条件后重新规划并再次确认；replan.description 写入 workflow.description，全部制作节点使用新内容；执行后不能改写制作前条件 | 真实浏览器修改航班人数后，旧计划不得 start，新 hash/revision 重新确认后才开始；旧服务器忽略 description 时读回检查直接阻止开始 |
| 5 来源报价、未知服务信息 | 来源 URL／checked_at／priceCurrency；路线缓存绑定起终点、位置、日期和时刻 | 缺坐标的资料仍展示，但不能画假点；缺报价不算免费；缺中转数不说直达；不平移原始班次；不编出租车上浮比例、油费或停车费；按每人／整车计费 | 无报价航班、无坐标酒店、手工体验、币种与计费单位的负向测试通过；公开信息不代表实时库存 |
| 6 开始制作／进度／失败／恢复 | POST workflows/{id}/start；execution snapshots/events；planning/retry 或 execution/retry | 后端 start 校验 expected_hash/revision；前端复用同一 request ID；运行中轮询，失败停止动画并显示真实原因；采用不得在 running/failed/cancelled 提交 | 当前真实青森已到行程阶段，但最终手记失败；禁止把已有研究或阶段成稿当最终完成 |
| 7 每日成稿／展开、编辑、拖动重排／阶段确认 | stage-review 绑定 artifact ID/hash；最终 approve-output；随后 travel-revisions | 导出保留用户重排；最终整理保留所有已确认事实；采用前编辑保存在受保护草稿，最终稿返回后做字段级合并；同字段冲突需要重看；修订及个人保存回执成功才进入攻略动画 | 模型验证顺序、个人原话、当前事实与最终文字均保留；Chrome/WebKit 验证阶段和最终采用分开、失败重试，不跳页 |
| 8 攻略／来源／完整附录／保存 | validated travel_plan_v2；travel-revisions.client_state；读回保存 artifact 验证 ID/hash 和 sanitized state | 不遗漏完整 journal、每日标题、季节交通建议、预算估算或补充摄影参考；保存失败保留标题和弹层；恢复按钮不遮挡保存；成功后才进入手记 | 真实五天草稿已导出完整 Markdown，仍标为阶段稿；本地保存回执及丢字段拒绝测试通过；真实最终保存尚未通过 |
| 9 旅行手记／封面、日记、照片、批注、待办、实用附录、预算与总结 | bounded client_state；文档／图片上传 receipt；既有 travel artifact revisions | 本机受保护文件 + 完成后的云端版本保存；个人状态不能另造实际 facts/events；未知费用与 FX 待核对；实际支付、转账均须用户输入；录音无转写时只保存原件，不假装已识别 | 页面、预算和已有订单关联通过；没有银行转账、支付执行或可靠实时 FX 服务，不显示这些操作成功 |
| 9 导出／版本 | KML/GPX/JSON export；native printNotebook；history artifacts/content | 地图导出仅含已知坐标；文字 PDF 从当前已采用的 owner/execution/artifact/hash 内容生成，完整 Unicode 分页；导出前先保存；非图文排版 PDF | Native 长中文多页末尾测试通过；文字版明确标注，照片和纸质版式仍在应用内查看；不会加载不可信网页执行打印 |
| 10 从手记进入这趟旅行／游前准备 | Notebook 的 JourneyLink；client_state.tripSession.phase/preparation | 攻略不能绕过手记直达旅程；开始旅行先等待保存，阶段失败留在游前；出发安排快照保留 | Chrome/WebKit 的游前进入和开始失败／重试通过；QA 不自动声明真实出发 |
| 10 今日安排／留片段／调整余下／实际进度 | canonical action + travel-revisions；progress/action_id；个人记录 client_state | 实际开始／结束取服务端回执；失败保持原状态；已完成、取消、锁定与已有订单按后端约束保护；未来调整保留版本记录 | 实际进度、改排、重复计费保护及失败重试回归通过；没有伪造完成事实 |
| 10 结束旅行／回顾／分账 | 先保存 phase=after，再显示回顾；总结／账本 client_state | 结束失败保留确认弹层和旅行中阶段；回顾预览不提前确认；个人原话与账目持续保留 | 结束失败／重试与旅行回顾通过；银行到账属于用户记录，不是系统执行结果 |
| 唯一保留的照片处理 | native ImageStudio／ImageWorkbench；owner-bound image action／receipt；authenticated hash-checked image download | 原有裁剪、修复、文字、图层、批处理、撤销、草稿和导出保留并换成现设计；签名 action token 留在 native | 本任务原生入口通过；既有本地照片／生命周期检查保留；联网照片处理本轮未跑，不能称完整线上处理通过 |

## 需要修正的偏离及本地落点

| 编号 | 偏离 | 补齐位置／核验 |
|---|---|---|
| D01 | 交通页增加的意向、来源或已有订单没送给制作任务 | production/preparation.js + travelRequestDescription；模型及交通重新确认检查 |
| D02 | replan 只记 instruction，制作仍读旧 description | ReplanRequest.description、旅行限定／执行后保护、workflow.description；API 检查各节点 query |
| D03 | start 接收版本字段却未执行校验 | native API 传 hash/revision；后端传入既有 execution authority 校验；旧 hash/revision 409 |
| D04 | 响应丢失后的创建／启动 ID 不持久 | protected draft 中保存同一请求身份；QCP 创建复用；REST 可选 request_id 重放与请求体冲突检查 |
| D05 | 重开任务可能沿用另一任务的个人草稿 | 每个 workflow 的账号／对话哈希文件；native 先验证归属；恢复当前任务／失配导出／无草稿条件复核 |
| D06 | 保存导出恢复原 action 排序，拖动没到后台 | exportTravelDocument 分辨无改动与用户结构重排；同步日期 ISO 和 days 标题 |
| D07 | 采用最终成稿会覆盖采用前用户修改 | captureEdits + mergeTravelEdits；完成后的修订／个人状态 receipt；冲突不自动覆盖 |
| D08 | 保存先跳页，失败无法原地重试 | NoteSaveSheet await；commitPersonal 及完整 readback；恢复提示不遮挡按钮 |
| D09 | 开始／结束旅行仅本地变阶段 | beginJourney/endJourney await 个人状态保存；phase 失败不推进 |
| D10 | 实际进度操作立即返回且隐藏失败 | await canonical progress receipt；任务切换隔离／刷新；失败显示并保留原事实 |
| D11 | 最终笔记可改掉人数、预算、日期、每日资料等已确认字段 | finalize_travel_notebook 冻结全部 approved 内容；仅追加笔记文字、合法照片引用和待核对问题 |
| D12 | 缺坐标或缺报价导致有来源资料丢失，地图空值崩溃或字段被当确定值 | 服务 parser、NearbyMap、酒店／航班详情保留未知；不声称未知中转为直达 |
| D13 | route schema 缺币种，缓存串不同起终点 | priceCurrency schema、routeQueryKey、任务重置隔离与原始班次绑定 |
| D14 | 假费用上浮／固定油费停车费／未知变 0／整车按人数乘／来源币种丢失 | 费用显示保留未知，取消虚构估价；显式计费单位优先；服务记录携带来源／币种；手工体验空费不是免费 |
| D15 | WebKit window.print 不形成可用导出 | owner/hash 绑定的 native 文字 PDF；全字符串分页或明确拒绝；原生末尾检验 |
| D16 | 完整 journal 和附录没有全部在前端可读 | 完整攻略、摄影参考、实践建议和估算 Disclosure；保留最终补充文字 |
| D17 | 已确认的 53337 字符真实行程被 48000 单项上游限制拒绝 | 本地 worker 使用既有 96000 上下文保护、不截断；相关测试通过；当前服务器未部署，真实最终手记仍失败 |

D01–D17 均已给出本地实现和测试。D17 的线上闭环未完成，D02/D03/个人状态的新服务器行为也不能在未部署时宣称已生效。没有用“偏离率 0%”表达这种情况。

## 验证与仍需完成的工作

后端两组测试合计 **151 passed**（104 + 47，SQLite／临时文件隔离）；前端模型 **43** 项；Chrome/WebKit **138** 项页面检查，**114** 次 axe、0 页面错误／0 违规。iOS 模拟器当前四项唯一测试通过：长中文 PDF 分页、个人保存回执校验、入口／四导航／照片入口、同一青森任务的真实只读失败状态。1010 个包内资源与当前源包逐一 SHA 一致，原生关键源码／配置匹配构建快照。证据为同目录 summary.json、各 report.json、native-*-summary.json 及截图。

真实任务仍为 `wf_850913895443090c7f670cc566ab3a36`／`wfr_ecf90f87bec24f898fdc35e4fd630a14`。研究、五天行程与阶段确认已完成（69 项安排、12 来源）；最终手记 **failed，66%**，`travel_itinerary` 53337 字符超过当前服务器 48000。最新模拟器仍显示这条实际失败并禁用最终采用。完整攻略草稿在 ../aomori-live/aomori-five-day-guide-draft.md，属于阶段稿。实际出行日期、时间、订单与游玩状态均未代填。

剩余：获得明确外部写入授权后，将有限后端修复合入服务器实际版本并建立回滚点；不能用本任务旧基线整文件覆盖服务器较新版本。部署后继续同一任务，验证最终手记、采用、云端保存及真实步骤 8–10。还需联网照片处理与真机最大字号／GPS／语音权限验收。供应商实时库存、实际购票／预约、支付、银行及实时 FX 没有现成能力，本实现提供公开资料、渠道入口和用户既有记录，不虚构交易成功。

本任务未 commit、push 或部署。用户 AGENTS 第 5 条明确要求这些外部动作事先授权；此前的授权问题尚未收到答复，继续本地梳理不构成授权。
