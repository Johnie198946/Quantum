# Quantum HTML 工具：租户 Coder、设计 Skill 与章节插图完成记录

- 日期：2026-09-24
- 目标：复用既有 PPT 治理工作流，完成 iOS 可发起/审批/预览/下载/分享的 HTML 工具链；Coder 可在当前认证租户沙箱内修改任意代码层；HTML 设计必须实际加载设计 Skill；章节插图必须由当前段落及相邻上下文驱动并先核验 Prompt。
- 发布状态：待本记录对应提交推送并按精确 SHA 部署后更新。

## 已实现

1. HTML 工作流扩展为：需求分析 → UI/UX 设计审批 → 章节插图 Prompt 核验 → 自包含 SVG 插图 → 自包含 HTML → 最终验收。
2. `ui-ux-pro-max`、`claude-design`、`popular-web-designs`（含 Apple 模板）和 `design-md` 作为版本化只读 Skill pack 随平台发布，进入租户 Hermes 模板。
3. 运行时在每个设计、插图和 HTML 节点前强制读取上述 Skill，计算 SHA-256，并写入 `skill_load` 回执；缺失即失败，不再只把 Skill 名称写进 Prompt。
4. Coder 节点开放文件读取、写入、精确补丁、搜索和命令执行；所有文件路径只允许租户工作区相对路径。
5. 命令执行由独立 root-owned runner 承担；Bridge 不加入 Docker 组。Runner 只接受本地 Unix socket，请求路径必须匹配服务端认证身份派生的 tenant/user namespace。
6. 每条命令运行于一次性容器：无网络、只读根文件系统、移除全部 capabilities、`no-new-privileges`、PID/CPU/内存限制，仅挂载当前租户 workspace；`HOME`、`TMPDIR` 与 `/app` 均由隔离 tmpfs 覆盖，不暴露平台源码或 Docker socket。
7. 文件工具拒绝绝对路径、`..`、symlink 和 root 外 canonical path；写入采用同目录原子替换。
8. 插图上下文由服务端从源文档确定性选择当前段落及前后段；Prompt 必须包含主体、语义关系、必含元素、禁止元素、风格、构图、可读性和无障碍说明，并绑定上下文 digest。
9. SVG 插图禁止脚本、外链、`href/src`、`foreignObject`，要求 `viewBox/title/desc`，并绑定已核验 Prompt SHA-256；最终 HTML 只能在治理占位符处嵌入该插图，之后再次执行 HTML CSP/外链/网络 API 安全门禁。
10. 部署脚本新增 runner unit 安装、精确 API 镜像绑定、启停、回滚快照和恢复逻辑。

## 验证

- Python/Bridge/工作流/部署契约定向回归：`224 passed`。
- 新增租户边界、Prompt、SVG、Skill 加载及 runner 安全测试：通过。
- `ruff`：通过。
- Python `compileall`：通过。
- `bash -n scripts/update.sh`：通过。
- `git diff --check`：通过。
- iOS iPhone 17 Pro 模拟器定向 XCTest：`1 executed, 0 failures`，`TEST SUCCEEDED`。
- 全量 `tests` 探测：`2370 passed, 30 skipped, 42 failed, 99 errors`；失败集中于既有测试环境/依赖和无关模块（例如 Starlette/httpx TestClient 版本不兼容、鉴权/数据库 fixture、既有内容抽取与发布测试），不作为本变更的通过门禁；本变更触及的定向集合已独立通过。

## 发布与回滚

- 目标提交 SHA：本文件所在的不可变提交；部署回执记录实际 40 位 SHA。
- GitHub `main`：推送后填写。
- Active release：部署后填写。
- Rollback release：部署前服务器 CAS 记录后填写。
- 生产探针：部署后填写，包括 runner systemd 状态、真实隔离命令、跨租户/逃逸拒绝、设计 Skill 回执、插图 Prompt/SVG/HTML 契约、API/Bridge/Worker/公网健康及源码/镜像 SHA 对齐。

## 已知边界

- Coder 的完整能力仅作用于当前租户 workspace；不允许直接修改平台仓库、Hermes 全局目录、部署目录或其他租户目录。
- 命令容器以当前 attested API 镜像作为语言工具链来源，但 `/app` 被 tmpfs 覆盖；不继承宿主凭据、网络或 Docker socket。
- HTML 仍受 512 KB 单文件上限及现有严格 CSP 约束。
