# server-health-fixes-20261009 completion

task_id: server-health-fixes-20261009
status: TESTED
branch: codex/server-health-fixes-20261009
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/server-health-fixes-20261009
head/local_commit: 基线6b143ded4efcc7f9913c9a71e35658efa172d44b；修复尚未提交
remote_sha: 本任务分支尚未推送
server_before: 7b3a2b17c3b1e6fc196808116cf0f27174a7024f；/opt/releases/ai-lab-platform-7b3a2b17c3b1.nN4yon；286份运行文件一致，8/8容器healthy，当前无活动任务
server_after: 未部署
health_check: 部署前健康，部署后待验证
functional_check: 本地360项PASS、1项Mac缺/proc跳过；静态检查/脚本语法/diff检查PASS；真实功能待部署后验证
rollback_point: 部署前建立；原release与4个Python镜像已记录server-before.json
remaining_risks: 没有长时间峰值压测；cloud-init脚本原始来源仍未知，不能臆测后盲目重跑；认证预算不重启认证服务

## 目标、授权与架构

用户要求修复同一事故体检发现的问题，延续本次事故明确给出的提交、推送和部署修复授权；不合并main，不覆盖其他任务。另开独立Worktree/分支以保留前次修复及其未提交验收记录，初始922edc0，编辑前快进5abc59c；开发期间进一步快进吸收线上6b143ded的相邻工作流修复，两次都保留本任务文件。用户一任务一分支/Worktree要求优先于旧tracked main-only规则。盘点见ops/acceptance/server-health-fixes-20261009/worktree-inventory.txt，实际部署基线见server-before.json。

需求为部分实现。继续复用SQLite存储、持久事件、账务outbox、Compose、systemd原生slice和现有update.sh CAS/锁/回滚。没有新业务服务、平行存储或第三方依赖。

## 变更

- scripts/chat_run_store.py：原子待处理队列上限复用HERMES_MAX_QUEUE，后台保留前台队列位；低内存/近cgroup上限/低磁盘空间拒绝新工作而仍允许幂等回放。轻量SQL领取、选中后读取payload；is_background在原表加法迁移并回填，保留前台优先、session串行、owner限制与重试策略。提取既有事件投影到同事务helper，恢复重试耗尽时状态与唯一error事件一起提交；过期与耗尽状态部分索引避免周期扫描历史payload。
- scripts/hermes_bridge.py、backend/api/chat.py：HTTP429/503可重试繁忙响应与SSE错误；明确未入队时退还预留额度，既有断线/取消仍保留待对账策略。
- backend/services/durable_usage_recovery.py：在既有事件表加终止事件部分索引，实际恢复查询测试证明不再扫描非终止历史或临时排序。
- docker-compose.yml：所有现有服务加入应用父slice，各容器内存/swap/PIDs边界、10MiB×3日志轮转。
- ops/systemd/quantum-runtime.slice、system-authen.slice.d/60-memory-budget.conf及两份Hermes service：应用总预算和既有认证slice预算。配置与峰值依据见resource-budget.md。
- scripts/update.sh：复用managed_units回滚保护新预算；应用认证预算不重启认证；少于5GiB拒绝新发布；健康验收后受同一锁执行旧release可恢复归档。
- scripts/release_retention.py：只处理可识别、未被引用、超过14天的旧源码release，保留最新7份/当前/直接回滚；不跟随data链接，归档完整读验后才移除原目录，归档保留；不执行docker prune或删除用户数据。
- 相关测试覆盖跨实例并发入队、幂等、后台预留、资源压力、迁移优先级、失败重放/答案块、账务退还、真实HTTP429、真实恢复查询计划、共享数据归档隔离与保留策略。原status测试补齐临时状态映射路径，避免写宿主机/opt。

## 验证与回滚

360项相关测试PASS，1项Linux锁/proc验证在Mac跳过；ruff backend/scripts/tests PASS，bash -n update.sh PASS，git diff --check PASS。无新增依赖或基础镜像变更；准备从已核验6b143ded生产镜像增量复制改动文件，并核验整个运行时代码哈希。

回滚恢复原release/镜像标签/attestation与managed unit文件、认证原live属性；保留新增SQLite列和索引及当前持久数据，禁止用旧数据库覆盖后来任务。归档可恢复，当前与本轮回滚版本不归档。服务超预算可能在应用cgroup内终止而不会承诺任意负载永不重启。

## 并行发布保护

第一次部署在CAS前发现实际版本已为7b3a2b，未建立回滚点、未改镜像标签或服务。已合并对方工作流事件重试修复，重新核验286份代码与8个容器；本轮部署基线更新为7b3a2b17c3b1e6fc196808116cf0f27174a7024f，server-before.json记录实际release和镜像。先前360测试有效，另对合并工作流进行相关回归，86项PASS。
