# 无监督出版标准流程

本文件是出版流程的统一规范入口，覆盖角色职责、交接协议、失败恢复和验收边界。复用既有 Workflow、publication store、交接台账、审核证明和 watchdog；配置入口为 `config/quantumn-daily-publication.json`，不另建调度器。底层字段校验以对应代码为准，修改实现时必须同步本规范与角色提示词；旧操作手册只保留命令参考，不再独立定义调度或角色职责。

## 职责与顺序

1. 采集任务至少得到 1 个可用候选即可成功，栏目覆盖可缺省。持久化 CONTENT_AVAILABLE 收据，收据不是写作素材。
2. 编译任务通过现有 canonical Wiki / knowledge gateway 提供可引用正文。优先本轮已编译内容；未选中候选编译失败不阻断本期，可回退已有授权知识。无可用正文时明确等待。
3. 选题后冻结本期引用输入。写作 agent 只交内容（标题、摘要、正文、来源、必要的真实执行材料），不填写系统元数据、审核结果或发布状态。
4. 程序从原生 cron 会话及程序注入的发行请求（或已受管 Workflow execution）绑定作者会话、主题、发行日及 slot，生成 editorial brief、学习目标、发行键、权利/证明控制字段。按体裁确定要求；预检失败通过现有持久化 revision outbox 返回写作修改，最多 3 次。
5. 素材任务只补双封面及三张正文插图，不冒充原作者。独立审核通过现有原生证明；main 使用原有审核协议，Story 使用 story-supervision-v2 和 supervision。 修订合同保留旧缺口为 open，独立签名 review 通过 gap_resolutions 逐项说明真实补证或合理收缩范围；程序随后关闭已有缺口账本，不回写冻结合同或让作者补状态。审核时间同属程序字段：完整验证签名后，从原生会话结束时间生成 UTC 时间；原始审核文件及哈希保持不变，不依赖模型填写时区。
6. 程序 finalize → 到期 release → 逐期正文和五媒体读回。全部应发 slot 通过才报告完成。任务暂停、缺失、跨 profile 不支持及重试耗尽均不能报成功。

时间安排：采集 01:00，收据目标 02:00，异步编译目标 03:00。watchdog 每 2 分钟检查当天全部期次并提前准备；作者每次实际开始时冻结本期输入，08:05 等固定作者 cron 是额外唤醒，不是阻止提前写作的时间门禁。ai-toolkit 先满足至少一个候选可用的采集条件，再优先使用已编译正文；新候选尚未编译时可使用既有授权知识，不以采集回执代替正文。发行以各主题 release_times 为准，到期才发布；写作/素材/审核应在对应 slot 前完成，延期保留原 issue_key，不借下一期掩盖。公共审核轮询每 10 分钟，公共到期发行每 5 分钟，由 store 判断是否到期，不为每个主题硬编码发行 cron。配置文件不会自动修改 cron，新增主题复用已绑定角色并由 watchdog 轮转。

## 增删主题

增加 `series` 行：稳定 id、title、kind=daily、enabled、genre、release_times、starts_on（可选）、execution_enabled；本机主题绑定 author_job_id / author_profile、素材 job、review_job_id / review_profile；服务器受管 Workflow 主题才绑定 workflow_schedule_id，不可将远端会话冒充本机作者。多时段采用独立 issue_key，12:00 保留旧日期键。修改配置后同步客户端和服务端并重启对应进程。

下线使用 enabled=false，保留元数据和已发行内容。不要删除有历史记录的行。发行时间修改只影响新计划，须先处置已冻结/排队旧期。

author_profile=story 使用本机 Story 原生 cron 和独立 supervision 审核；主 watchdog 只通过原生 `hermes -p <profile> cron run` 派发并读取对应 profile 的执行账本。发行传输与恢复账本仍由 default 管理，不复制凭据。

## 写作交付契约

受管 Workflow 产物采用 `publication-content-v1`（兼容已有 `ai-toolkit-publication-content-v2`，不接受未声明的其他版本）：只输出内容协议允许的标题、摘要、Markdown 正文、来源文档及确有发生的执行材料。执行/调度/期次/作者身份由平台读取，不从正文猜测，也不接受 agent 自报审核通过。图片代理读取已经冻结的正文和来源，不重写正文。

本地内容入口 `publication_editorial_remote.py start` 的 submission 仅需 `title`、`summary`、`source_files`、`execution_files`；程序补 brief/objectives，正文目录及主题/日期/slot 由调度传参。旧六字段入口保留兼容，不应继续要求新写作任务生产那两个系统字段。

## 故障恢复与激活验收

暂停/缺失先修复原 cron 状态或绑定，不消耗恢复次数。重试耗尽后只能针对精确 claim 使用 watchdog 的 `--rearm-key KEY --expected-attempts N --material-hash HASH --reason TEXT`；必须失败且原 owner 已终止，无活跃执行，旧记录保留审计历史。禁止清库重置全部次数。

上线前：确认服务端与本地脚本同一版本；建立回滚点；绑定真实原生作者会话/独立 reviewer；修复 Story failure_deliver 的无效路由；恢复素材任务；仅重置已核验的失败 claim。现有稿件正文质量仍须修改，不降低门槛。

生产验收必须创建下一分钟的一次性真实任务，留下同一 issue_key 的 scheduler run、作者原生会话、artifact、系统字段、素材、独立审核证明、finalize、release、读者正文与五媒体响应及重复触发幂等证据。测试后删除临时 job。

本任务的 `publication-standard-timed-check.json` 是真实 Hermes 定时触发的隔离集成测试（使用合成审核/素材 fixtures），只验证调度与程序链路，不代表真实内容和生产出版验收。用户已于本任务授权推送、部署和真实定时验收；最终状态以 completion manifest 为准。

2026-09-27 真实验收使用 ai-toolkit/tang-history 的临时 00:01 时隙，两篇均已通过真实作者、独立审核、自动发行和正文/五媒体回读。验收后移除此临时时隙，保留历史记录；正常时隙为主栏目每日12:00、Story每日08:00/13:00/20:00。测试中修复过系统缺陷并重启定时恢复，不声称原测试全程未中断。


## 交接协议与字段所有权

这些是现有入口的合同说明，不是新增服务或新协议版本。运行任务必须引用本规范及对应角色提示词；写入文档不等于现有 cron 已自动重新加载。

| 环节 | 责任方与输入 | 必须交付 | 校验与下一步 |
| --- | --- | --- | --- |
| 采集 | 采集 cron；配置的候选来源 | 至少1个可用候选与 CONTENT_AVAILABLE 收据；区分 saved/queued/compiled | 不要求各主题齐备；不得把排队或收据冒充已编译正文 |
| 编译/选题 | 既有知识入口；已保存候选或授权知识 | 可读、可引用的来源正文；冻结本期选中输入 | 无正文就等待；非本期选中候选失败不扩大为全栏目失败 |
| 作者请求 | 程序 `author-input` | `PUBLICATION_CONTENT_REQUEST`：series_id、issue_date、issue_key、issue_slot、release_at、author_job_id | 由配置及服务端期次生成；无任务返回 NO_NEW_DRAFT |
| 作者内容 | main/Story；只读本期请求、来源与返工缺口 | `publication-content-v1` 的六个字段：schema_version、title、summary、body、source_documents、execution_documents；文档项仅 kind/content | 来源列表非空；真实执行材料按体裁需要。禁止添加批准、发行、身份及状态字段；校验器在 `backend/services/publication_workflow_handoff.py` |
| 作者回执 | 作者完成当前原生会话 | `publication_content_result` 仅含 series_id、issue_date、issue_slot、artifact_file；前三项原样回显请求 | 程序验证真实终态、请求匹配、路径和产物哈希，生成 `publication-native-author-v1` 身份绑定；回显不构成作者自行决定期次的授权 |
| 素材/prepare | 素材角色；冻结正文及来源 | shelf_cover、reader_cover、illustration_01..03、image-manifest.json 与真实生成证据 | 素材角色不改正文或作者；start 构建合同，prepare 返回 issue/revision/attempt/target_hash；正文、来源、素材共同受审核绑定 |
| 独立审核 | 独立 reviewer；`PUBLICATION_REVIEW_REQUEST` 精确指定的本期材料 | 原始审核 JSON、publication_review_result 回执；按实际请求绑定目标及 publication_material_hash（若提供） | 读取全部正文与五图证据；拒绝则结构化 research_gaps；已有 open 缺口通过 gap_resolutions 逐项确认；不得 stage、改合同或自签名 |
| 证明/入库 | 程序；已结束的真实原生审核会话 | native-editorial-review-v2 等实际请求版本的签名证明及验证后的审核 envelope | 核验公钥、全文输入、最终输出、身份、原始字节哈希和目标；reviewed_at 从签名 native_ended_at 派生，保留原 review/proof 字节 |
| 暂存/发行 | 既有 finalize、operator、release_due | 通过门禁的 staged/scheduled edition；到期后 published 与发行回执 | 到期不是审核通过；单期失败不阻断其他合格期；重复执行不能重复发布 |
| 读者交付 | 服务端投影与实际客户端 | 正文、封面、插图可见；认证、媒体响应及版本一致 | 服务端有图片或返回200只证明接口可用；客户端必须接收字段、鉴权取图并渲染，另行完成UI验收 |

`editorial_brief`、学习目标、issue/revision/attempt、目标哈希、作者身份、审核时间和发布状态由程序或可信运行记录生成/验证。权利依据必须来自已有授权记录；程序生成控制字段不等于产生内容授权。审核者负责内容判断，不负责补系统字段。

修改协议必须同时核对生产者、消费者、验证器、相关测试和角色提示词，不以文档中宣称新版本代替实现。不得要求作者兼容消费者的临时系统字段缺失。

## 状态、失败与幂等

沿用现有台账：内容等待素材 → prepare/await_review → rejected 或 approved → staged/scheduled → published。不同文件有各自状态值，不强行另建统一状态机。以服务端原 attempt/edition 为准，cron completed 只表示一次执行完成。

内容返修最多三轮；既有恢复 claim 的基础设施尝试上限为6，按期次、材料与阶段计数，两者不能混用。基础设施错误先恢复同一冻结材料；内容拒绝交回原作者，继承原缺口和失败历史。无法安全自动恢复时保留原文件并明确阻断，禁止清库、伪造通过、换期次隐藏缺刊或改已发布正文。

每次交付应保存期次、原生执行ID、产物哈希、审核与证明哈希、edition、实际发布时间及读回结果。变更配置先核对在途期次；已发布历史不随时隙删除而消失。

## 图片交付协议与验收分层

当前新每日出版物要求五图：shelf_cover 1440×2560、reader_cover 2560×1440、illustration_01..03 各1600×900；实际格式、大小和哈希由现有媒体验证器检查。旧版本可能没有完整媒体，不能把占位装饰当作已交付的生成图片。

- 书架 JSON：`shelf_cover_url` 指向 `/api/v1/knowledge-publications/{id}/covers/shelf_cover`。
- 正文 JSON：`reader_cover_url` 指向同一路径族的 reader_cover；`illustration_urls` 列出 `/media/illustration_01..03`。插图列表不等于已插入 Markdown；客户端不得仅扫描正文图片语法。
- 媒体接口需要认证及可见性检查。客户端应复用既有认证请求，不将私有媒体简单交给无认证的图片加载器，不向外部URL转发凭据。
- 现有插图列表没有章节锚点。当前可按接口顺序展示插图区域；若要求逐段精准编排，应先定义并实现审核绑定的锚点合同，不能凭客户端猜测把历史图插进正文。
- 缺失图片与加载失败须可区分；占位图不作为图片验收通过证据。历史补图须走可审计的新版本/补充流程，不静默覆盖已冻结版。

验收分为三层：A 原生自动执行与真实出版；B 读者API正文、媒体字节/哈希及认证边界；C 实际客户端书架封面、阅读封面和三张插图显示。任何完成报告必须逐层记录，A/B通过不能宣称C通过。2026-09-27的首轮闭环验证覆盖A/B，iOS图片可见性未验收；后续20本图片审计发现DTO和渲染消费缺口，详见本任务审计记录。


## PCM、Agent 规则与自动触发的关系

PCM 的 `bookshelf.search/open` 输出合同描述读者媒体字段；`publication.illustrated_delivery` consumption 登记既有自动出版及媒体消费的边界和验收，不增加可调用工具或第二运行时。它的状态包含客户端消费，不因服务端可执行或接口描述可读就标为端到端通过。操作规范负责解释实施顺序；`AGENTS.md` 只放必读入口及不能绕过的责任约束。

图片生成必须由已登记的自动出版角色执行。用户手动触发、人工补图、脚本直接调用模型的单次成功只能记录为手动验证。无人值守验收必须保存定时/控制器派发 → 精确素材请求 → 真实五图生成记录 → prepare → 独立审核 → 到期发行的同一期次证据，区分用户初次授权配置与每期人工干预；生产 cron 和测试一次性 cron 均须如实标明来源。

书架媒体字段为兼容性可选字段：旧无图版本仍能解码读取，但不应显示为已配图。已具备的图片由客户端认证下载并显示；正常出版 loop 中缺图不应让用户点击“生成图片”才能继续。

周期素材 cron 与控制器派发在同一个 recovery_claims 中领取精确材料预算；可信原生执行接管既有预约不重复计次，同一执行只能处理一个期次。按原生执行终态与冷却恢复，不把常驻 gateway PID 当作仍在配图。原生作者预脚本异常必须明确报告，不能用 NO_NEW_DRAFT 掩盖；已移除的历史时隙保留记录，但不参与当前已配置期次的作者等待判断。
