# 服务器反复无响应：代码与主机诊断

日期：2026-10-09；目标：t-react.com / 120.24.248.58。
审查基线：线上 release 3be75d49119912f6be2f456ce3ecb642167d4c84。Quantum 为多用户 API、持久聊天后台及工作流服务。本次沿“后台轮询→SQLite→Hermes→主机资源”路径诊断，按 2 核、实际可用 3499 MiB 的单机部署评估。

## 判断及置信度

已证实本次存在严重内存压力和磁盘等待；不是只凭 CPU 仪表盘推断。最强解释是内存压力下缓存页被反复回收、热循环又反复读取，造成主机级 I/O 拥堵，使 HTTP、TLS 和 SSH 都无法及时响应。SQLite 连接未及时关闭与后台历史全表扫描是已复现的代码缺陷，会放大这条链路。

尚未证实：故障前最后一笔匿名内存增长由哪个 PID 引起；不能声称两个补丁已独立证明消除所有复发，也不能将昨日 OOM 等同于今日故障。

## 必须处理：连接没有确定释放，空队列持续读历史表

位置：scripts/chat_run_store.py 的 _connect / claim_next；scripts/chat_run_worker.py 的 main。

- 原 _connect 返回 sqlite3.Connection，19 个存储调用点使用 with。Connection 上下文只处理事务，不关闭连接；缓存和句柄需等待垃圾回收。
- 本机默认垃圾回收开启、合成 16 MiB 数据表、200 次查询：修复前峰值 26.3→173.1 MiB，仍存活 40 个连接；修复后 23.9→35.2 MiB，0 个存活连接。不是永久无界泄漏的证明，而是可复现的延迟释放和内存峰值放大。
- 线上空闲时 worker 打开 70 个 hermes_chat_runs.sqlite3 句柄、58 个 WAL 句柄。不能从该快照推断故障时峰值。
- claim_next 每 0.1 秒执行一次；数据库没有以 status 起始的可用队列索引。线上 EXPLAIN 返回 SCAN chat_runs。2415 条历史任务，任务表约 35.3 MiB，其中叶页约 6.9 MiB，事件表约 16.3 MiB。
- 线上读取采样 rchar 60.79 MiB/s、实际 read_bytes 0 MiB/s。采样时有 1 个 active run，不能称该两秒完全空闲；主循环在未占满线程时仍轮询空队列。此前时段确认队列为空。rchar 含缓存读取，不能当作磁盘吞吐；它说明热循环在缓存失效后有大量重复读取需求。
- 故障时段 16:00–19:30 没有新 chat run，上一条在 10:27:20。因此“用户高并发直接触发本次故障”没有证据，后台空转必须纳入原因。

本地最小修复：共享 _connect 改为确保事务退出后 finally close，异常和设置失败也关闭；在既有初始化内新增仅覆盖 queued/stalled 且 attempt<2 的部分索引。保持既有 claim 排序、每用户和每会话限制、重试、账务与事件存储路径。没有改变部署、并行度或生产数据库。

## 必须处理：主机资源预算不闭合

- 实际 RAM 3499 MiB；swap 2047 MiB；/etc/sysctl.conf 与 /etc/sysctl.d/99-sysctl.conf 设置 vm.swappiness=0。
- 18:15:59 可用内存 94980 KiB（约 92.75 MiB），负载 49.55，blocked=39，CPU iowait=41.89%。磁盘读 110982.38 KiB/s，平均队列 166.63，await=88.11 ms；page scan/steal 显著升高；整个时段 swap 使用与换入换出均为 0。
- journald 连续报告 Under memory pressure, flushing caches，最后至少到 18:38:38。
- 8 个 Docker 服务 Memory/MemoryReservation/MemorySwap=0，表示未设限；6 个 Authen 服务 MemoryHigh/Max=infinity。Bridge 有 High=1152 MiB、Max=1280 MiB；worker High=700 MiB、Max=800 MiB。已存在部分限制，不能说所有进程都无界。
- 这不证明某个容器泄漏；但当前预算无法保证为系统、数据库缓存和入口服务保留足够空间。swappiness=0 不是绝对禁用 swap，事实是本次压力期确实没有使用 swap。

最小后续：根据实测常驻内存设置现有服务预算，评估合理 swappiness；不把扩容或提高所有上限当作代码缺陷的替代修复。

## 必须处理：资源保护器会永久失去采样

生产专有文件：/usr/local/sbin/ai-lab-resource-guard、/etc/systemd/system/ai-lab-resource-guard.service 与 timer，仓库未找到同名实现。

unit TimeoutStartUSec=infinity；script 的 docker curl 有 4 秒超时，但整体执行没有超时。它只记录警告，没有降载或恢复行为。18:04:51 最后一次完成：mem_available=407056 KiB、load=3.03；18:06:22 再次启动后直到重启没有完成。一旦 oneshot 持续 active，timer 无法启动下一轮。

不能从日志确定它卡在 systemctl、logger 还是其他调用，也不能说该 guard 自身造成了宕机。最小后续是为既有 unit 加 TimeoutStartSec，并留足独立诊断能力；不是新建另一套守护服务。

## 应处理：后台执行绕过接口并发门禁

scripts/chat_run_worker.py 默认 MAX_WORKERS=8，每用户 MAX_PARALLEL=3，直接调用 bridge._run_agent_sync。接口 _admit_request 只出现在 endpoints.py；HERMES_MAX_CONCURRENCY=2 不限制 durable worker。线上没有设置 HERMES_CHAT_WORKER_THREADS，默认 8 生效；agent cache 实际为 4，不能把源码默认 32 当生产值。

具体失败场景：单用户三个独立会话可同时执行；多个用户可占满八个线程，超过接口层声明的两个。该缺口在有任务时放大风险，但本次故障期间无新 run，不能认定是直接触发。本地补丁没有擅自改变用户并行行为；后续应按整个单机的并发预算收敛既有入口。

## 反例与排除

- 正确密钥仍在 SSH banner 之前超时，认证错误不足以解释；直连且关闭代理仍复现，浏览器代理也不足以解释。
- 本次没有持久化记录可确认 global OOM。VNC 所见 Killed process 属于 2026-10-08 17:09:18 的 jev-live-route-probe2-20261008.service cgroup OOM，不能用作今日同进程证明。
- 当前物理读 0 和健康恢复说明缓存充足时热循环可隐藏；因此重启后的健康检查不能排除反复资源耗尽。
- 10 月 9 日重启由云平台正常模式受理；20:09 的另一次重启不是本任务发起，操作者未知。

## 验证

- tests/test_chat_run_store.py：21 passed，新增关闭/回滚/提交及查询计划测试。
- 存储、worker、chat status、knowledge adapter：143 passed；第一次有 1 个旧测试因 /opt 生产路径不可写失败，设置 HERMES_STATE_DB_MAPPING_FILE 到临时路径后全部通过，未改测试绕过断言。
- Bridge、chat stream API、note illustrations、durable usage recovery：101 passed。合计 244 项相关回归通过。
- CI 的 Ruff backend/ scripts/ tests/ 全量检查通过；git diff --check 通过。
- 合成 2401 条 terminal 历史记录，50 次空队列查询：有索引平均 0.461 ms，无索引 1.347 ms（本地温缓存，不代表生产冷磁盘性能）。
- 可复现脚本及 before/after 输出在本目录；脚本只创建临时合成数据，不读取用户聊天。
- 当前生产仍是原 SHA；API /health=ok version=0.8.0；此前公网健康、首页、SSH 和 8 容器通过。未发布补丁，未做生产压力测试或真实用户全流程。

未覆盖：整仓库安全/账务审计、iOS/前端构建、所有 Hermes 上游内部实现、故障瞬间进程分项内存。生产仍可能复发；修复后的线上效果必须另行部署并观察验证。
