# Revision68 旅行功能与 PCM / Chat 对照

原型版本：revision68；模板：`quantum.travel.revision68@1`；逐项登记 216 个功能。正式登记位于 PCM `consumptions.yaml` 的 `travel.prototype_revision68`，本表由同一登记生成。

工作流：入口 → 悬浮对话收敛 → 景点文件夹 → 完善计划 → 确认旅行计划 → 交通预订 → 制作 → 采用 → 攻略保存进笔记 → 手记 → 进入这趟旅行。

保存前沿用 `travel.revise` 的成果版本；保存后采用 `travel.notebook.update` 的笔记 CAS、已有私人索引和回执。Chat 可发现并确认同一组能力。普通追问走已登录 Chat；选择、重排、动画属于消费端操作，并通过 client_state 保存。外部预订链接仅供用户核对和录入实际订单。

| 功能 ID | 页面 | 功能 | PCM 能力 |
|---|---|---|---|
| travel.r68.s01.f01 | 入口 | 旅行空间卡片 | `workflow.status`, `workflow.open`, `artifact.open`, `artifact.download` |
| travel.r68.s01.f02 | 入口 | 右上角新建 | `workflow.status`, `workflow.open`, `artifact.open`, `artifact.download` |
| travel.r68.s01.f03 | 入口 | 任务列表 | `workflow.status`, `workflow.open`, `artifact.open`, `artifact.download` |
| travel.r68.s01.f04 | 入口 | 打开已有旅行 | `workflow.status`, `workflow.open`, `artifact.open`, `artifact.download` |
| travel.r68.s01.f05 | 入口 | 任务状态与失败原因 | `workflow.status`, `workflow.open`, `artifact.open`, `artifact.download` |
| travel.r68.s01.f06 | 入口 | 照片任务入口 | `workflow.status`, `workflow.open`, `artifact.open`, `artifact.download` |
| travel.r68.s01.f07 | 入口 | 旧任务成果只读导出 | `workflow.status`, `workflow.open`, `artifact.open`, `artifact.download` |
| travel.r68.s02.f01 | 悬浮对话 | 输入旅行想法 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f02 | 悬浮对话 | 发送与追问 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f03 | 悬浮对话 | 需求字段收敛 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f04 | 悬浮对话 | 日期未定保留 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f05 | 悬浮对话 | 出发城市 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f06 | 悬浮对话 | 目的地 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f07 | 悬浮对话 | 天数 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f08 | 悬浮对话 | 同行人数 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f09 | 悬浮对话 | 预算与币种 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f10 | 悬浮对话 | 兴趣选择 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f11 | 悬浮对话 | 节奏与交通偏好 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f12 | 悬浮对话 | 补充条件 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f13 | 悬浮对话 | 照片托盘 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f14 | 悬浮对话 | 语音输入 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f15 | 悬浮对话 | 需求总结确认 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s02.f16 | 悬浮对话 | 收敛后展示景点卡片 | `workflow.create`, `workflow.clarification.read`, `workflow.clarification.respond`, `photo.import`, `voice.record` |
| travel.r68.s03.f01 | 景点文件夹 | 景点浏览 | `workflow.clarification.respond` |
| travel.r68.s03.f02 | 景点文件夹 | 长按卡片详情 | `workflow.clarification.respond` |
| travel.r68.s03.f03 | 景点文件夹 | 来源核对 | `workflow.clarification.respond` |
| travel.r68.s03.f04 | 景点文件夹 | 收藏与取消 | `workflow.clarification.respond` |
| travel.r68.s03.f05 | 景点文件夹 | 已有兴趣状态 | `workflow.clarification.respond` |
| travel.r68.s03.f06 | 景点文件夹 | 筛选与搜索 | `workflow.clarification.respond` |
| travel.r68.s03.f07 | 景点文件夹 | 补充景点 | `workflow.clarification.respond` |
| travel.r68.s03.f08 | 景点文件夹 | 继续完善计划 | `workflow.clarification.respond` |
| travel.r68.s04.f01 | 完善与确认计划 | 旅行需求编辑 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f02 | 完善与确认计划 | 日期范围选择 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f03 | 完善与确认计划 | 预算金额和币种 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f04 | 完善与确认计划 | 出发交通偏好 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f05 | 完善与确认计划 | 兴趣补充 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f06 | 完善与确认计划 | 待办创建 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f07 | 完善与确认计划 | 待办完成与取消 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f08 | 完善与确认计划 | 待办排序 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f09 | 完善与确认计划 | 待确认提示 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f10 | 完善与确认计划 | 确认完善计划 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f11 | 完善与确认计划 | 计划读取 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f12 | 完善与确认计划 | 确认旅行计划 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f13 | 完善与确认计划 | 修改需求重新规划 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s04.f14 | 完善与确认计划 | 进入交通预订 | `workflow.clarification.read`, `workflow.clarification.respond`, `workflow.plan.read`, `workflow.approve`, `workflow.revise` |
| travel.r68.s05.f01 | 路线与交通 | 逐日路线 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f02 | 路线与交通 | 日历与日期调整 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f03 | 路线与交通 | 日期顺序调整 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f04 | 路线与交通 | 长按行程重排 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f05 | 路线与交通 | 事项详情 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f06 | 路线与交通 | 人工修改事项 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f07 | 路线与交通 | 新增交通段 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f08 | 路线与交通 | 移除尚未发生事项 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f09 | 路线与交通 | 起终点修改 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f10 | 路线与交通 | 航班城市与机场 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f11 | 路线与交通 | 往返日期和人数 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f12 | 路线与交通 | 舱等与航班偏好 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f13 | 路线与交通 | 真实来源航班比较 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f14 | 路线与交通 | 地图路线展开 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f15 | 路线与交通 | 公交铁路与步行方案 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f16 | 路线与交通 | 打车自驾与包车 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f17 | 路线与交通 | 轮渡与登山路线 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f18 | 路线与交通 | 道路距离和费用未知状态 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f19 | 路线与交通 | 票券与通票核对 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f20 | 路线与交通 | 路线摘要采用 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s05.f21 | 路线与交通 | Google Earth KML 导出 | `travel.revise`, `travel.notebook.update`, `artifact.download`, `share.present` |
| travel.r68.s06.f01 | 住宿餐饮体验与预订 | 住宿日期人数房间 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f02 | 住宿餐饮体验与预订 | 住宿位置与周边地图 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f03 | 住宿餐饮体验与预订 | 住宿偏好筛选 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f04 | 住宿餐饮体验与预订 | 酒店方案比较 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f05 | 住宿餐饮体验与预订 | 餐厅搜索与偏好 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f06 | 住宿餐饮体验与预订 | 用餐时间与禁忌 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f07 | 住宿餐饮体验与预订 | 活动体验搜索 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f08 | 住宿餐饮体验与预订 | 营业窗口与时长 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f09 | 住宿餐饮体验与预订 | 新增自定义体验 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f10 | 住宿餐饮体验与预订 | 项目加入行程 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f11 | 住宿餐饮体验与预订 | 预订链接跳转 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f12 | 住宿餐饮体验与预订 | 待预订清单 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f13 | 住宿餐饮体验与预订 | 已有订单录入 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f14 | 住宿餐饮体验与预订 | 渠道和确认号 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f15 | 住宿餐饮体验与预订 | 订单关联事项 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f16 | 住宿餐饮体验与预订 | 明确已外部预订确认 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f17 | 住宿餐饮体验与预订 | 预订时间冲突提示 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f18 | 住宿餐饮体验与预订 | 自动记录费用 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f19 | 住宿餐饮体验与预订 | 修改或撤销已有记录 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s06.f20 | 住宿餐饮体验与预订 | 完成交通回到制作入口 | `travel.revise`, `travel.notebook.update`, `share.present` |
| travel.r68.s07.f01 | 生成与采用 | 开始制作 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f02 | 生成与采用 | 计划 hash 与版本校验 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f03 | 生成与采用 | 稳定请求编号防重 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f04 | 生成与采用 | 生成进度 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f05 | 生成与采用 | 节点状态与 Token 预算 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f06 | 生成与采用 | 已完成成果读取 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f07 | 生成与采用 | 来源与逐日块核对 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f08 | 生成与采用 | 失败原因展开 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f09 | 生成与采用 | 原任务失败步骤续作 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f10 | 生成与采用 | 查看成稿 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f11 | 生成与采用 | 成稿逐日编辑 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f12 | 生成与采用 | 成稿顺序调整 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f13 | 生成与采用 | 阶段复核与继续生成 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f14 | 生成与采用 | 最终成果采用 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f15 | 生成与采用 | 审批后个人编辑合并 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f16 | 生成与采用 | 照片墨迹和采用动效 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s07.f17 | 生成与采用 | 进入攻略 | `workflow.start`, `workflow.status`, `workflow.artifacts.list`, `workflow.review`, `workflow.retry`, `travel.revise` |
| travel.r68.s08.f01 | 攻略与笔记模板保存 | 攻略总览 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f02 | 攻略与笔记模板保存 | 沿途逐日展开 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f03 | 攻略与笔记模板保存 | 完整安排 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f04 | 攻略与笔记模板保存 | 预订快捷入口 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f05 | 攻略与笔记模板保存 | 行前核对 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f06 | 攻略与笔记模板保存 | 待办查看 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f07 | 攻略与笔记模板保存 | 预算入口 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f08 | 攻略与笔记模板保存 | 资料来源与待确认问题 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f09 | 攻略与笔记模板保存 | 保存手记标题 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f10 | 攻略与笔记模板保存 | 选择封面 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f11 | 攻略与笔记模板保存 | 选择日记与附录内容 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f12 | 攻略与笔记模板保存 | 保存为真实私人笔记 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f13 | 攻略与笔记模板保存 | 幂等复用原笔记 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f14 | 攻略与笔记模板保存 | 保存回执失败留在编辑 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f15 | 攻略与笔记模板保存 | 笔记库重新打开 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f16 | 攻略与笔记模板保存 | 换 Chat 后读取原笔记 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f17 | 攻略与笔记模板保存 | 模板版本识别 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s08.f18 | 攻略与笔记模板保存 | 未知日期坐标不补造 | `travel.notebook.save`, `knowledge.note.read`, `travel.notebook.update` |
| travel.r68.s09.f01 | 旅行手记编辑与阅读 | 封面 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f02 | 旅行手记编辑与阅读 | 每天日记切换 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f03 | 旅行手记编辑与阅读 | 记录文字 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f04 | 旅行手记编辑与阅读 | 导入照片 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f05 | 旅行手记编辑与阅读 | 拍照记录 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f06 | 旅行手记编辑与阅读 | 原始录音附件 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f07 | 旅行手记编辑与阅读 | 照片和录音排版 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f08 | 旅行手记编辑与阅读 | 已有记录编辑 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f09 | 旅行手记编辑与阅读 | GPS 附件 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f10 | 旅行手记编辑与阅读 | 整本标题副标题封面编辑 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f11 | 旅行手记编辑与阅读 | 每日章节标题编辑 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f12 | 旅行手记编辑与阅读 | 剩余安排编辑 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f13 | 旅行手记编辑与阅读 | 保留实际历史 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f14 | 旅行手记编辑与阅读 | 历史版本查看 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f15 | 旅行手记编辑与阅读 | 阅读选中内容 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f16 | 旅行手记编辑与阅读 | 高亮与批注 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f17 | 旅行手记编辑与阅读 | 批注列表 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f18 | 旅行手记编辑与阅读 | 引用内容问 Chat | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f19 | 旅行手记编辑与阅读 | 日记助手建议 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f20 | 旅行手记编辑与阅读 | 人工确认助手建议 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f21 | 旅行手记编辑与阅读 | 天气来源与更新时间 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f22 | 旅行手记编辑与阅读 | 资料附件 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f23 | 旅行手记编辑与阅读 | 实用附录 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f24 | 旅行手记编辑与阅读 | 文字 PDF 导出 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f25 | 旅行手记编辑与阅读 | 复制分享摘要 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s09.f26 | 旅行手记编辑与阅读 | 保存时安排与当前安排对照 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read`, `photo.import`, `photo.capture`, `voice.record`, `file.upload`, `share.present` |
| travel.r68.s10.f01 | 进入这趟旅行 | 打开这趟旅行 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f02 | 进入这趟旅行 | 证件入境保险核对 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f03 | 进入这趟旅行 | 交通预订核对 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f04 | 进入这趟旅行 | 天气开放备选核对 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f05 | 进入这趟旅行 | 资料与待确认问题展开 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f06 | 进入这趟旅行 | 开始这趟旅行 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f07 | 进入这趟旅行 | 保留出发时安排 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f08 | 进入这趟旅行 | 当天日期切换 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f09 | 进入这趟旅行 | 下一个事项 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f10 | 进入这趟旅行 | 打开各事项详情 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f11 | 进入这趟旅行 | 开始事项 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f12 | 进入这趟旅行 | 完成事项 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f13 | 进入这趟旅行 | 取消事项 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f14 | 进入这趟旅行 | 跳过事项 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f15 | 进入这趟旅行 | 延后事项 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f16 | 进入这趟旅行 | 真实进度回执 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f17 | 进入这趟旅行 | 快捷记录碎片 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f18 | 进入这趟旅行 | 调整剩余安排 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f19 | 进入这趟旅行 | 调整原因 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f20 | 进入这趟旅行 | 调整前后对照 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f21 | 进入这趟旅行 | 明确确认调整 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f22 | 进入这趟旅行 | 当天票据记录 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f23 | 进入这趟旅行 | 当地位置与交通来源 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f24 | 进入这趟旅行 | 一句话记账 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f25 | 进入这趟旅行 | 结束旅行确认 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f26 | 进入这趟旅行 | 游后回顾预览 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f27 | 进入这趟旅行 | 个人总结 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f28 | 进入这趟旅行 | 按已有记录起草总结 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f29 | 进入这趟旅行 | 保存总结 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f30 | 进入这趟旅行 | 计划与实际对照 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f31 | 进入这趟旅行 | 未核对费用与分账 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f32 | 进入这趟旅行 | 确认最终回顾 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f33 | 进入这趟旅行 | 返回今日安排 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s10.f34 | 进入这趟旅行 | 返回在路上 | `travel.notebook.update`, `travel.revise`, `knowledge.note.read` |
| travel.r68.s11.f01 | 预算与分账 | 预算币种和汇率 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f02 | 预算与分账 | 手动汇率核对 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f03 | 预算与分账 | 成员增删与重命名 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f04 | 预算与分账 | 预计费用与实际花费 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f05 | 预算与分账 | 分类筛选 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f06 | 预算与分账 | 手动新增费用 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f07 | 预算与分账 | 一句话识别费用 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f08 | 预算与分账 | 语音记账 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f09 | 预算与分账 | 快捷指令账目同步 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f10 | 预算与分账 | 人工核对识别结果 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f11 | 预算与分账 | 撤销费用 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f12 | 预算与分账 | 修改账目 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f13 | 预算与分账 | 付款人选择 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f14 | 预算与分账 | 参与人选择 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f15 | 预算与分账 | 均分 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f16 | 预算与分账 | 按金额分账 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f17 | 预算与分账 | 按比例分账 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f18 | 预算与分账 | 转账与结算 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f19 | 预算与分账 | 余额与未核对提示 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f20 | 预算与分账 | 多币种原币保存 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f21 | 预算与分账 | 费用 CSV 导出 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s11.f22 | 预算与分账 | 账本随旅行笔记持久化 | `travel.notebook.update`, `travel.revise`, `voice.record`, `share.present` |
| travel.r68.s12.f01 | 照片处理保留并换肤 | 导入与拍照 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f02 | 照片处理保留并换肤 | 裁切与旋转 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f03 | 照片处理保留并换肤 | 主体提取 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f04 | 照片处理保留并换肤 | 去背景 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f05 | 照片处理保留并换肤 | 修复与滤镜 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f06 | 照片处理保留并换肤 | 文字与叠加层 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f07 | 照片处理保留并换肤 | 图层调整 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f08 | 照片处理保留并换肤 | 批量处理 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f09 | 照片处理保留并换肤 | 撤销重做 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f10 | 照片处理保留并换肤 | 草稿保存与恢复 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f11 | 照片处理保留并换肤 | 原图保留 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f12 | 照片处理保留并换肤 | 结果导出 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |
| travel.r68.s12.f13 | 照片处理保留并换肤 | 签名动作及处理回执 | `photo.import`, `photo.capture`, `media.process`, `media.save_edit`, `artifact.download`, `share.present` |

验证边界：不得把本地演示、未知日期的建议、未知坐标的文字地点、尚未发生的游后回顾当作实地进度。文字 PDF 保留完整 Unicode 内容，应用内保留原型图文布局。功能验证结果记录在本任务 completion manifest。
