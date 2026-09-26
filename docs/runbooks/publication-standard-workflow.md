# 无监督出版标准流程

本变更复用既有 Workflow、publication store、交接台账、审核证明和 watchdog。配置入口为 `config/quantumn-daily-publication.json`；不另建调度器。

## 职责与顺序

1. 采集任务至少得到 1 个可用候选即可成功，栏目覆盖可缺省。持久化 CONTENT_AVAILABLE 收据，收据不是写作素材。
2. 编译任务通过现有 canonical Wiki / knowledge gateway 提供可引用正文。优先本轮已编译内容；未选中候选编译失败不阻断本期，可回退已有授权知识。无可用正文时明确等待。
3. 选题后冻结本期引用输入。写作 agent 只交内容（标题、摘要、正文、来源、必要的真实执行材料），不填写系统元数据、审核结果或发布状态。
4. 程序从原生 cron 会话及程序注入的发行请求（或已受管 Workflow execution）绑定作者会话、主题、发行日及 slot，生成 editorial brief、学习目标、发行键、权利/证明控制字段。按体裁确定要求；预检失败通过现有持久化 revision outbox 返回写作修改，最多 3 次。
5. 素材任务只补双封面及三张正文插图，不冒充原作者。独立审核通过现有原生证明；main 使用原有审核协议，Story 使用 story-supervision-v2 和 supervision。
6. 程序 finalize → 到期 release → 逐期正文和五媒体读回。全部应发 slot 通过才报告完成。任务暂停、缺失、跨 profile 不支持及重试耗尽均不能报成功。

时间安排：采集 01:00，收据目标 02:00，异步编译目标 03:00。watchdog 每 2 分钟检查当天全部期次并提前准备；作者每次实际开始时冻结本期输入，08:05 等固定作者 cron 是额外唤醒，不是阻止提前写作的时间门禁。ai-toolkit 先满足至少一个候选可用的采集条件，再优先使用已编译正文；新候选尚未编译时可使用既有授权知识，不以采集回执代替正文。发行以各主题 release_times 为准，到期才发布；写作/素材/审核应在对应 slot 前完成，延期保留原 issue_key，不借下一期掩盖。公共审核轮询每 10 分钟，公共到期发行每 5 分钟，由 store 判断是否到期，不为每个主题硬编码发行 cron。配置文件不会自动修改 cron，新增主题复用已绑定角色并由 watchdog 轮转。

## 增删主题

增加 `series` 行：稳定 id、title、kind=daily、enabled、genre、release_times、starts_on（可选）、execution_enabled；本机主题绑定 author_job_id / author_profile、素材 job、review_job_id / review_profile；服务器受管 Workflow 主题才绑定 workflow_schedule_id，不可将远端会话冒充本机作者。多时段采用独立 issue_key，12:00 保留旧日期键。修改配置后同步客户端和服务端并重启对应进程。

下线使用 enabled=false，保留元数据和已发行内容。不要删除有历史记录的行。发行时间修改只影响新计划，须先处置已冻结/排队旧期。

author_profile=story 使用本机 Story 原生 cron 和独立 supervision 审核；主 watchdog 只通过原生 `hermes -p <profile> cron run` 派发并读取对应 profile 的执行账本。发行传输与恢复账本仍由 default 管理，不复制凭据。

## 写作交付契约

受管 Workflow 产物采用 `publication-content-v1`（旧 ai-toolkit-content-v1 兼容）：只输出内容协议允许的标题、摘要、Markdown 正文、来源文档及确有发生的执行材料。执行/调度/期次/作者身份由平台读取，不从正文猜测，也不接受 agent 自报审核通过。图片代理读取已经冻结的正文和来源，不重写正文。

本地内容入口 `publication_editorial_remote.py start` 的 submission 仅需 `title`、`summary`、`source_files`、`execution_files`；程序补 brief/objectives，正文目录及主题/日期/slot 由调度传参。旧六字段入口保留兼容，不应继续要求新写作任务生产那两个系统字段。

## 故障恢复与激活验收

暂停/缺失先修复原 cron 状态或绑定，不消耗恢复次数。重试耗尽后只能针对精确 claim 使用 watchdog 的 `--rearm-key KEY --expected-attempts N --material-hash HASH --reason TEXT`；必须失败且原 owner 已终止，无活跃执行，旧记录保留审计历史。禁止清库重置全部次数。

上线前：确认服务端与本地脚本同一版本；建立回滚点；绑定真实原生作者会话/独立 reviewer；修复 Story failure_deliver 的无效路由；恢复素材任务；仅重置已核验的失败 claim。现有稿件正文质量仍须修改，不降低门槛。

生产验收必须创建下一分钟的一次性真实任务，留下同一 issue_key 的 scheduler run、作者原生会话、artifact、系统字段、素材、独立审核证明、finalize、release、读者正文与五媒体响应及重复触发幂等证据。测试后删除临时 job。

本任务的 `publication-standard-timed-check.json` 是真实 Hermes 定时触发的隔离集成测试（使用合成审核/素材 fixtures），只验证调度与程序链路，不代表真实内容和生产出版验收。用户已于本任务授权推送、部署和真实定时验收；最终状态以 completion manifest 为准。

当前验收临时增加 ai-toolkit/tang-history 的 00:01 时隙，便于验证已经到期的真实发行；验收后移除此临时时隙并保留历史记录。
