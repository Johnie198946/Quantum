# 资源预算与回滚

生产是2核、3499 MiB内存、2047 MiB swap。原Native Bridge MemoryPeak920 MiB、worker391 MiB；Authen整个system-authen.slice峰值442 MiB。当前Docker服务合计约370 MiB，API此前采样251 MiB。

复用systemd原生slice，Quantum Docker服务与Bridge/worker合计MemoryHigh2304 MiB、MemoryMax2560 MiB、SwapMax1280 MiB；认证复用既有system-authen.slice High512、Max640、SwapMax256 MiB。两组硬内存上限总3200 MiB，余299 MiB与未分配swap留给系统；新工作在host可用低于约500 MiB或cgroup接近上限时拒绝。High触发回收而非直接杀死，Max用于保护宿主机。容器另有限额，API768、Postgres384、三个业务worker各256、taskboard256、frontend64、redis64 MiB，swap各为内存的附加等量预算；总量受父slice约束，不把所有单项峰值相加当成可同时使用容量。

父slice保留前次Native各项上限1280/800 MiB；实际设置需部署后核对内核cgroup文件和两个并发诊断任务。历史峰值有限，不能替代长时间业务压测。单服务超过边界可能被cgroup终止，不能承诺任意负载服务都不重启；它的目的是把故障限制在应用组内，SSH不在该组。

update.sh的既有managed_units备份扩展至父slice、认证dropin与set-property产生的三个system.control配置，另外记录认证原live属性。失败时恢复原配置、live属性和原release，再用原Compose恢复原cgroup位置。正常认证预算应用不重启认证进程。

日志每容器10MiB×3。发布目录保留最新7份、14天内全部、当前/直接回滚版本、进程与容器挂载引用；更旧可识别release压缩成root私有、完整读校验后的tar.gz，保留共享data链接而不跟随。归档不删除，仍可恢复；自动发布在根盘少于5GiB时拒绝，入队在少于1GiB时拒绝，防止持续部署耗尽空间。没有docker prune或删除用户数据。
