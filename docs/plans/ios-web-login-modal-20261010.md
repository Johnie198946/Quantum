# QuanSyn App 授权登录与轻量对齐

Authen 是平台统一鉴权服务。已核对 KnowlegeGragh/Authen 的 origin/main 与生产 /opt/authen 的 auth/main.py、JWT 代码指纹完全一致；旧 UserAuthen 副本不作依据。

验证码、请求归属、五分钟期限、确认/取消、一次性票据由 Authen 现有 Redis 和认证接口管理。Quantum 沿 external_auth 代理原 Authen JWT，不另签用户令牌、不新增数据库表或服务；已有 OAuth 流程保留。请求按手机号和入口 IP 限流，未知账号返回同样形式。只有该账号已登录的人类凭证才能确认，重复消费被 Redis 原子操作拒绝；API 日志屏蔽验证码、state、ticket。

iOS 复用官方 Logo、主题、Keychain 和前台 AppRoot：中心展开300ms、六位码收拢、登录中字样和逆时针环；真实确认成功且至少3秒后才显示对勾，用户关闭。失败可重试，取消通知 Authen。网页沿现有设计和 AuthContext 轮询并兑换 Authen 一次性票据，短信入口保留。

QuanSyn 结果使用已有同账号结果入库/回传路径，Mac 和服务器读相同记录立即对齐；保留 claim/revision/导入回执和 request_id 去重，成功导入后清理临时输入，不复制整套聊天库。18:00/18:10 属于旧知识库双向任务，并非临时传递队列。18:00 因知识导出治理停用，不扩大本次授权去解除。18:10 既有回流脚本修复 SSH 复用、失败即停止、冲突路径排除和回执状态；只安装既有入口，不建第二个调度。

架构门禁通过：capability_gateway 沿现有 capability_handlers 入口；native/Skill 契约归回已有 contracts 模块，knowledge 缩至1500行以内，保持所有调用/错误处理并以相关回归验证。无新依赖。

真实隔离服务、实际网页和模拟器完整登录/取消验收均通过，凭证仅在隔离环境生成和使用。生产发布前合并08ff1774服务器最新提交、复跑相关检查、核对远端SHA并建立回滚点。
