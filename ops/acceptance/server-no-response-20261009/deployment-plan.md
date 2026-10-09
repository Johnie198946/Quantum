# 生产修复执行计划

状态：待用户明确授权提交、push 与部署；当前未发布。

## 已审查变更

- chat_run_store.py：确定释放 SQLite 连接，保留事务语义；新增 claimable 部分索引。数据不删除。
- chat_run_worker.py：线程数上限服从现有 HERMES_MAX_CONCURRENCY；当前生产值 2；任务继续排队。
- ai-lab-resource-guard.service drop-in：TimeoutStartSec=30s、TimeoutStopSec=5s。只约束现有保护器，不新增进程。
- sysctl drop-in：vm.swappiness=20；原值0。提高内存压力下使用既有2GiB swap的意愿，不禁用或重建swap。

## 已完成验证与回滚准备

247项存储/worker/Bridge/状态/知识/账务相关测试通过；123项部署测试通过、1项平台依赖跳过；Ruff backend/scripts/tests全量通过；git diff --check通过。systemd-analyze在服务器临时目录验证合并的超时配置通过，尚未加载。

rollback_point=/opt/ai-lab-shared/rollbacks/server-no-response-20261009-preflight.Lijcsv，root:root权限700。包含原release路径、SHA、原swappiness运行值、配置归档、两个拟修改文件的原版/不存在标记，以及通过SQLite quick_check的任务库一致性备份；备份只留服务器，不下载用户数据。

预期原release=/opt/releases/ai-lab-platform-3be75d491199.4EgBAP，SHA=3be75d49119912f6be2f456ce3ecb642167d4c84。执行前必须重新检查，若已被其他任务切换则停止并重新评估。

## 授权后的顺序

1. 仅显式暂存本任务文件，commit任务分支；只push该任务分支，git ls-remote核对SHA，不合并main。
2. 导出精确SHA源码归档与SHA256。通过既有update.sh离线source入口发布；使用同一部署锁和expected-current-SHA防并发切换。
3. 4个Python服务目前共用镜像sha256:a005bc8b08dd00671a62e030da656c0262dd37df25da196b62338b59fc531415。仅两份运行时脚本改变、Dockerfile及依赖不变，可在此已验证基线镜像上复制精确SHA的改动文件并标注新revision；不在生产重装依赖。保留原镜像ID、原标签及原attestation作为回滚点。若源文件/依赖基线不吻合则不使用增量镜像。
4. 任务排空后通过既有不可变release切换与健康/数据库契约检查；失败走既有自动rollback。临时镜像准备和attestation切换也需在同一锁内并纳入回滚。
5. 安装两个已验证的资源配置文件，daemon-reload与sysctl -p仅加载本文件；实际值必须核对20、30s/5s。记录原值，失败恢复这些文件和运行值。
6. 公网TLS/health、API ready、Bridge health、8容器、SSH和认证入口检查；做隔离诊断会话的真实持久聊天/事件回读，不读取现有用户内容。检查worker线程数2、连接数不再周期性堆积、claim使用索引、rchar与RSS/available/load，观察至少数个保护器周期。未完成真实功能检查不能标VERIFIED。

## 风险与边界

并发下降可能增加排队时间；swappiness20不能保证低内存时性能，不能宣称完全消除复发。Docker与Authen原无限上限未凭单个静态快照随意改小，避免大文档/既有任务突然OOM；首先部署已证实的热循环和连接释放修复，测量修复后的占用。若仍出现压力，需要进一步用进程采样核对而非再次仅重启。

服务器磁盘14GiB可用；增量镜像不需要重新下载大型Office依赖。Mac的Docker daemon当前未运行，不能声称本机镜像构建已通过。
