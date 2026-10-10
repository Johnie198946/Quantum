// Visual components and interactions adapted directly from the supplied App.tsx.
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "../../auth/AuthContext";
import { platformApi } from "../../services/platformApi";
function Icon({ name, size = 20 }) {
  const paths = {
    arrow: <path d="m5 12 14 0m-5-5 5 5-5 5" />,
    bolt: <path d="m13 2-9 12h7l-1 8 9-12h-7l1-8Z" />,
    book: <>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" />
      </>,
    chart: <path d="M4 19V9M10 19V5M16 19v-7M22 19V3M2 19h22" />,
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m9 18 6-6-6-6" />,
    code: <path d="m8 9-4 3 4 3m8-6 4 3-4 3m-3-9-2 12" />,
    copy: <>
        <rect width="13" height="13" x="9" y="9" rx="2" />
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
      </>,
    file: <>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
        <path d="M14 2v6h6M8 13h8M8 17h5" />
      </>,
    image: <>
        <rect width="18" height="18" x="3" y="3" rx="3" />
        <circle cx="9" cy="9" r="1.5" />
        <path d="m4 17 4.5-4.5 3 3 2-2L20 20" />
      </>,
    laptop: <>
        <rect width="16" height="11" x="4" y="4" rx="2" />
        <path d="M2 19h20M9 19v1h6v-1" />
      </>,
    link: <>
        <path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.2 1.2" />
        <path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.2-1.2" />
      </>,
    logo: <>
        <path d="M7.5 4.5A3.5 3.5 0 0 1 11 1h2a3.5 3.5 0 0 1 0 7H9.5A2.5 2.5 0 0 0 7 10.5v3A3.5 3.5 0 0 1 3.5 17H2" />
        <path d="M16.5 19.5A3.5 3.5 0 0 1 13 23h-2a3.5 3.5 0 0 1 0-7h3.5a2.5 2.5 0 0 0 2.5-2.5v-3A3.5 3.5 0 0 1 20.5 7H22" />
      </>,
    logout: <>
        <path d="M10 17l5-5-5-5M15 12H3" />
        <path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" />
      </>,
    menu: <path d="M4 7h16M4 12h16M4 17h10" />,
    more: <>
        <circle cx="5" cy="12" r="1" fill="currentColor" stroke="none" />
        <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
        <circle cx="19" cy="12" r="1" fill="currentColor" stroke="none" />
      </>,
    paperclip: <path d="m21.4 11.6-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5" />,
    phone: <>
        <rect width="12" height="20" x="6" y="2" rx="2.5" />
        <path d="M10 18h4" />
      </>,
    search: <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>,
    send: <path d="m22 2-7 20-4-9-9-4Zm0 0L11 13" />,
    shield: <>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
        <path d="m9 12 2 2 4-5" />
      </>,
    spark: <path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5ZM19 15l.7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7Z" />,
    text: <>
        <path d="M5 4h14M12 4v16M8 20h8" />
      </>,
    video: <>
        <rect width="15" height="14" x="3" y="5" rx="2" />
        <path d="m18 10 4-2v8l-4-2" />
      </>,
    wifi: <path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 20h.01M2 9a14 14 0 0 1 20 0" />
  };
  return <svg
    aria-hidden="true"
    className="shrink-0"
    fill="none"
    height={size}
    viewBox="0 0 24 24"
    width={size}
    stroke="currentColor"
    strokeLinecap="round"
    strokeLinejoin="round"
    strokeWidth="1.7"
  >
      {paths[name]}
    </svg>;
}
function Brand({ dark = false }) {
  return <div className={`brand ${dark ? "brand-dark" : ""}`}>
      <span className="brand-mark"><img src="/quansyn/logo.png" alt="Quantum" /></span>
      <span>QuanSyn</span>
    </div>;
}
function LoginPage({ error, report }) {
  const { loginWithPhone } = useAuth();
  const [busy, setBusy] = useState(false);
  const [count, setCount] = useState(0);
  const [connectPhase, setConnectPhase] = useState("idle");
  const connectRun = useRef(0);
  useEffect(() => () => { connectRun.current += 1; }, []);
  useEffect(() => {
    if (!count) return;
    const timer = setTimeout(() => setCount(count - 1), 1e3);
    return () => clearTimeout(timer);
  }, [count]);
  async function action(fn) {
    setBusy(true);
    report("");
    try {
      await fn();
      return true;
    } catch (e) {
      report(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  function sendCode() {
    return action(async () => {
      await platformApi.sendPhoneCode({ phone: account });
      setCount(60);
    });
  }
  async function connectQuantum() {
    if (connectPhase !== "idle" || busy || count) return;
    const run = ++connectRun.current;
    const started = Date.now();
    setConnectPhase("loading");
    const success = await sendCode();
    await new Promise((resolve) => setTimeout(resolve, Math.max(0, 1200 - (Date.now() - started))));
    if (run !== connectRun.current) return;
    setConnectPhase(success ? "success" : "error");
    await new Promise((resolve) => setTimeout(resolve, 1000));
    if (run !== connectRun.current) return;
    setConnectPhase("restoring");
    await new Promise((resolve) => setTimeout(resolve, 300));
    if (run !== connectRun.current) return;
    setConnectPhase("idle");
    if (success) document.getElementById("password")?.focus();
  }
  const [account, setAccount] = useState("18576600894");
  const [password, setPassword] = useState("");
  const [featureDetail, setFeatureDetail] = useState(null);
  function submit(event) {
    event.preventDefault();
    action(() => loginWithPhone({ phone: account, code: password, allowPendingAgreement: true }));
  }
  return <main className="login-page">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <div className="particle-field" aria-hidden="true">
        {Array.from({ length: 18 }, (_, index) => <i key={index} style={{ "--i": index }} />)}
      </div>

      <section className="login-story">
        <Brand />
        <div className="story-copy">
          <span className="eyebrow">
            <Icon name="spark" size={15} /> 跨端流转，从未如此轻松
          </span>
          <h1>
            灵感不掉线，
            <br />
            <span>内容随你走。</span>
          </h1>
          <p>让 Mac、手机与浏览器无缝连接。文字、图片、文件，即刻出现在你的每一块屏幕。</p>
          <div className="feature-row">
            <button onClick={(event) => setFeatureDetail({
    description: "提交后在 App 或 Mac 手动拉取，完成后手动回传。",
    kind: "feature",
    meta: "手动拉取与回传",
    name: "跨端传递",
    sourceRect: event.currentTarget.getBoundingClientRect()
  })} type="button">
              <span className="feature-icon"><Icon name="bolt" /></span>
              <strong>跨端传递</strong>
              <small>需求与资料双向传递</small>
            </button>
            <button onClick={(event) => setFeatureDetail({
    description: "资料沿用 Quantum 账号与租户权限，配对设备可以随时撤销。",
    kind: "feature",
    meta: "Quantum 账号权限",
    name: "账号私有资料",
    sourceRect: event.currentTarget.getBoundingClientRect()
  })} type="button">
              <span className="feature-icon"><Icon name="shield" /></span>
              <strong>账号私有资料</strong>
              <small>内容只属于你</small>
            </button>
            <button onClick={(event) => setFeatureDetail({
    description: "连接 Mac、手机与浏览器，让内容在不同平台间连续流动。",
    kind: "feature",
    meta: "支持 macOS、iOS 与 Web",
    name: "全平台连接",
    sourceRect: event.currentTarget.getBoundingClientRect()
  })} type="button">
              <span className="feature-icon"><Icon name="link" /></span>
              <strong>全平台连接</strong>
              <small>随时随地访问</small>
            </button>
          </div>
        </div>
        <span className="story-foot">© 2026 QuanSyn · 让内容自由流动</span>
      </section>

      <section className="login-panel">
        <div className="mobile-brand"><Brand dark /></div>
        <form className="login-card" onSubmit={submit}>
          <div className="login-heading">
            <span className="online-dot" />
            <small>Quantum 账号认证</small>
          </div>
          <h2>欢迎回来</h2>
          <p>登录后继续你的跨端体验</p>

          <label htmlFor="account">手机号</label>
          <div className="input-shell">
            <input
    id="account"
    onChange={(event) => setAccount(event.target.value)}
    placeholder="输入 Quantum 账号手机号"
    autoComplete="tel"
    inputMode="tel"
    required
    type="text"
    value={account}
  />
            {account && <span className="input-check"><Icon name="check" size={14} /></span>}
          </div>

          <div className="label-row">
            <label htmlFor="password">验证码</label>
            <button className="text-button" disabled={busy || count > 0} onClick={sendCode} type="button">{count ? `${count}s` : "获取验证码"}</button>
          </div>
          <input
    id="password"
    onChange={(event) => setPassword(event.target.value)}
    placeholder="输入 6 位验证码"
    type="text"
    autoComplete="one-time-code"
    inputMode="numeric"
    pattern="[0-9]{6}"
    required
    value={password}
  />

          {error && <p className="qs-error" role="alert">{error}</p>}
          <button disabled={busy || connectPhase !== "idle"} className="primary-button" type="submit">
            进入 QuanSyn <Icon name="arrow" size={19} />
          </button>

          <div className="divider"><span>或</span></div>

          <div className="qs-login-connect-slot">
            <button className={`qs-login-connect is-${connectPhase}`} disabled={busy || count > 0 || connectPhase !== "idle"} onClick={connectQuantum} type="button" aria-label={connectPhase === "loading" ? "正在连接 Quantum" : connectPhase === "success" ? "验证码已发送" : connectPhase === "error" ? "连接失败" : count ? `${count}秒后可重新获取验证码` : "使用 Quantum 登录"} aria-busy={connectPhase === "loading"}>
              <span className="qs-connect-idle"><Icon name="phone" size={28} /><span>Quantum 登录</span></span>
              <svg className="qs-connect-ring" aria-hidden="true" viewBox="0 0 32 32"><circle cx="16" cy="16" r="11" /></svg>
              <svg className="qs-connect-check" aria-hidden="true" viewBox="0 0 32 32"><path pathLength="1" d="m9 16 5 5 9-10" /></svg>
              <span className="qs-connect-error" aria-hidden="true">×</span>
            </button>
          </div>
          <p className="signup-copy">
            首次使用？ <span>沿用 Quantum 手机账号</span>
          </p>
        </form>
        <div className="security-note">
          <Icon name="shield" size={16} /> 资料沿用 Quantum 账号权限
        </div>
      </section>
      {featureDetail && createPortal(
    <DetailDialog file={featureDetail} onClose={() => setFeatureDetail(null)} />,
    document.querySelector(".quansyn")
  )}
    </main>;
}
function DeviceCard({
  active,
  detail,
  icon,
  name,
  onClick
}) {
  return <button
    className={`device-card ${active ? "active" : ""}`}
    onClick={(event) => onClick(event.currentTarget.getBoundingClientRect())}
    type="button"
  >
      <span className="device-icon"><Icon name={icon} size={19} /></span>
      <span>
        <strong>{name}</strong>
        <small>{detail}</small>
      </span>
      <span className="status-idle" />
    </button>;
}
function CopyControl({
  className = "",
  content,
  report
}) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(content);
    } catch (error) {
      report?.(error.message || "复制失败，请手动选择文本");
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1e3);
  }
  return <button
    aria-label={copied ? "已复制" : "复制内容"}
    className={`answer-copy ${className} ${copied ? "copied" : ""}`}
    onClick={(event) => {
      event.stopPropagation();
      copy();
    }}
    type="button"
  >
      {copied && <span>已复制</span>}
      <i><Icon name={copied ? "check" : "copy"} size={14} /></i>
    </button>;
}
function CodeDetail({
  code,
  onClosed,
  sourceRect
}) {
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setExpanded(true));
    return () => window.cancelAnimationFrame(frame);
  }, []);
  function close() {
    setExpanded(false);
    window.setTimeout(onClosed, 360);
  }
  const panelStyle = {
    "--source-left": `${sourceRect.left}px`,
    "--source-top": `${sourceRect.top}px`,
    "--source-width": `${sourceRect.width}px`,
    "--source-height": `${sourceRect.height}px`
  };
  return <div className={`insight-overlay ${expanded ? "expanded" : ""}`} onMouseDown={close}>
      <section className="insight-panel code-detail-panel" onMouseDown={(event) => event.stopPropagation()} style={panelStyle}>
        <header>
          <div><span>代码详情</span><h3>代码块</h3></div>
          <button aria-label="关闭详情" onClick={close} type="button">×</button>
        </header>
        <p>查看和复制此次返回的完整代码。</p>
        <div className="detail-code">
          <div>
            <span><i /><i /><i /></span>
            <small>代码</small>
            <CopyControl className="code-copy" content={code} />
          </div>
          <pre><code>{code}</code></pre>
        </div>
        <footer>
          <span><Icon name="code" size={13} /> 代码</span>
          <CopyControl content={code} />
        </footer>
      </section>
    </div>;
}
function DetailDialog({
  file,
  onClose
}) {
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (!file) return;
    const frame = window.requestAnimationFrame(() => setExpanded(true));
    return () => window.cancelAnimationFrame(frame);
  }, [file]);
  if (!file) return null;
  function close() {
    setExpanded(false);
    window.setTimeout(onClose, 360);
  }
  const panelStyle = {
    "--source-left": `${file.sourceRect.left}px`,
    "--source-top": `${file.sourceRect.top}px`,
    "--source-width": `${file.sourceRect.width}px`,
    "--source-height": `${file.sourceRect.height}px`
  };
  return <div className={`insight-overlay ${expanded ? "expanded" : ""}`} onMouseDown={close}>
      <section className="insight-panel universal-detail-panel" onMouseDown={(event) => event.stopPropagation()} style={panelStyle}>
        <header>
          <div>
            <span>{file.kind === "device" ? "设备详情" : file.kind === "feature" ? "能力详情" : "文件详情"}</span>
            <h3>{file.name}</h3>
          </div>
          <button aria-label="关闭详情" onClick={close} type="button">×</button>
        </header>
        <div className="dialog-file-icon">
          <Icon name={file.kind === "device" ? "laptop" : file.kind === "feature" ? "spark" : file.name.endsWith(".png") ? "image" : "file"} size={26} />
        </div>
        {file.preview && <img className="qs-detail-image" src={file.preview} alt={file.name} />}
        <p>{file.meta}</p>
        {file.description && <p className="detail-description">{file.description}</p>}
        <dl>
          <div><dt>{file.kind === "device" ? "连接状态" : "来源"}</dt><dd>{file.kind === "device" ? file.description || "手动拉取" : "Quantum 账号资料"}</dd></div>
          <div><dt>安全性</dt><dd><span className="safe-dot" /> 账号私有</dd></div>
          <div><dt>{file.kind === "device" ? "最近同步" : "保存位置"}</dt><dd>{file.kind === "device" ? "手动确认导入" : "QuanSyn"}</dd></div>
        </dl>
        <div className="dialog-actions">
          <button onClick={close} type="button">关闭</button>
          {file.action && <button onClick={file.action} type="button">{file.actionLabel || "下载原件"} <Icon name="arrow" size={16} /></button>}
        </div>
      </section>
    </div>;
}
function DocumentSearch({
  docs,
  open,
  onClose,
  onSelect
}) {
  const [scope, setScope] = useState("all");
  const [query, setQuery] = useState("");
  const panelRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    let timer = window.setTimeout(onClose, 4200);
    const resetTimer = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(onClose, 4200);
    };
    const closeOutside = (event) => {
      if (!panelRef.current?.contains(event.target)) onClose();
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("mousemove", resetTimer);
    document.addEventListener("keydown", resetTimer);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("mousemove", resetTimer);
      document.removeEventListener("keydown", resetTimer);
    };
  }, [open, onClose]);
  if (!open) return null;
  const results = docs.filter((doc) => (scope === "all" || (scope === "image" ? doc.icon === "image" : doc.icon !== "image")) && `${doc.name} ${doc.description || ""}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="search-dock-expanded" ref={panelRef}>
      <section className="doc-search">
        <div className="search-input">
          <Icon name="search" size={20} />
          <input autoFocus onChange={(event) => setQuery(event.target.value)} placeholder="搜索文档、图片或传输记录" value={query} />
          <button aria-label="收起搜索" onClick={onClose} type="button"><Icon name="chevron" size={16} /></button>
        </div>
        <div className="search-scope">
          {[["all", "全部"], ["file", "文档"], ["image", "图片"]].map(([id, label]) => <button key={id} className={scope === id ? "active" : ""} onClick={() => setScope(id)} type="button">{label}</button>)}
          <span>按名称和内容查找</span>
        </div>
        <div className="search-results">
          <small>{query ? `找到 ${results.length} 项` : "最近访问"}</small>
          <div className="asset-grid">
          {results.slice(0, 6).map((doc) => <button key={doc.name} onClick={(event) => onSelect({
    ...doc,
    kind: "file",
    sourceRect: event.currentTarget.getBoundingClientRect()
  })} type="button">
              <span className={`asset-thumb ${doc.icon}`}><Icon name={doc.icon} size={22} /></span>
              <div><strong>{doc.name}</strong><small>{doc.meta}</small></div>
            </button>)}
          </div>
          {!results.length && <div className="empty-result">没有找到相关内容，换个关键词试试</div>}
        </div>
        <footer><span>数秒无操作将自动收起</span><span>⌘K 随时唤起</span></footer>
      </section>
    </div>;
}
function ExitDialog({
  onClosed,
  onLogout,
  sourceRect
}) {
  const [expanded, setExpanded] = useState(false);
  const [counting, setCounting] = useState(false);
  const [count, setCount] = useState(3);
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setExpanded(true));
    return () => window.cancelAnimationFrame(frame);
  }, []);
  useEffect(() => {
    if (!counting) return;
    const interval = window.setInterval(() => setCount((value) => Math.max(0, value - 1)), 1e3);
    const finish = window.setTimeout(onLogout, 3e3);
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(finish);
    };
  }, [counting, onLogout]);
  function close() {
    if (counting) return;
    setExpanded(false);
    window.setTimeout(onClosed, 360);
  }
  const panelStyle = {
    "--source-left": `${sourceRect.left}px`,
    "--source-top": `${sourceRect.top}px`,
    "--source-width": `${sourceRect.width}px`,
    "--source-height": `${sourceRect.height}px`
  };
  return <div className={`insight-overlay exit-overlay ${expanded ? "expanded" : ""}`} onMouseDown={close}>
      <section
    className={`insight-panel exit-panel ${counting ? "counting" : ""}`}
    onMouseDown={(event) => event.stopPropagation()}
    style={panelStyle}
  >
        <div className="exit-copy">
          <span className="exit-icon"><Icon name="logout" size={22} /></span>
          <h3>确定要退出 QuanSyn？</h3>
          <p>设备间的内容仍会安全保留，下次登录后可以继续访问。</p>
        </div>
        <div className="exit-actions">
          <button onClick={close} type="button">暂不退出</button>
          <button className="exit-confirm" onClick={() => setCounting(true)} type="button">
            <span className="exit-ring" />
            <Icon name="logout" size={18} />
            <b>{counting ? count : "确认退出"}</b>
          </button>
        </div>
        {counting && <small className="exit-count-label">{count} 秒后安全退出</small>}
      </section>
    </div>;
}
function TransferView({ items, files, devices, draft, setDraft, target, setTarget, busy, loading, error, send, upload, removeFile, removeItem, next, loadMore, refresh, connectMac, revokeDevice, onLogout, renderContent, openFile, agreementContent }) {
  const messages = [...items].filter((item) => item.target === target).reverse();
  const activeDevice = target === "ios" ? "phone" : "mac";
  function setActiveDevice(value) {
    setTarget(value === "phone" ? "ios" : "mac");
  }
  function pasteImages(event) {
    if (busy || agreementContent) return;
    const images = [...(event.clipboardData?.items || [])]
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile()).filter(Boolean);
    if (!images.length) return;
    event.preventDefault();
    const text = event.clipboardData.getData("text/plain");
    if (text) {
      const { selectionStart, selectionEnd } = event.currentTarget;
      setDraft(draft.slice(0, selectionStart) + text + draft.slice(selectionEnd));
    }
    attachFile(images);
  }
  const docs = items.flatMap((item) => item.files.map((file) => ({
    name: file.metadata?.original_name || file.filename,
    meta: `${(file.byte_size / 1024).toFixed(1)} KB · ${(/* @__PURE__ */ new Date(item.created_at + (/[Zz]|[+-]\d\d:\d\d$/.test(item.created_at) ? "" : "Z"))).toLocaleString("zh-CN")}`,
    description: item.text,
    icon: /\.(png|jpe?g|gif|webp)$/i.test(file.metadata?.original_name || file.filename) ? "image" : "file",
    file,
    item,
    action: () => openFile(file)
  })));
  const [searchOpen, setSearchOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerScale, setDrawerScale] = useState(0.82);
  const [exitRect, setExitRect] = useState(null);
  const [detailFile, setDetailFile] = useState(null);
  const [inputError, setInputError] = useState(false);
  const inputRef = useRef(null);
  const messageAreaRef = useRef(null);
  const workspaceRef = useRef(null);
  const sidebarRef = useRef(null);
  const scrollSampleRef = useRef({ time: performance.now(), top: 0 });
  const scrollStopTimerRef = useRef(null);
  const [scrollProgress, setScrollProgress] = useState(0);
  useEffect(() => {
    function handleShortcut(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
      if (event.key === "Escape") {
        setSearchOpen(false);
        setDetailFile(null);
      }
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);
  useEffect(() => {
    if (!drawerOpen) return;
    function syncDrawerScale() {
      const workspaceWidth = workspaceRef.current?.clientWidth || window.innerWidth;
      const drawerWidth = sidebarRef.current?.getBoundingClientRect().width || 240;
      setDrawerScale(Math.max(0.32, Math.min(0.94, (workspaceWidth - drawerWidth - 14) / workspaceWidth)));
    }
    syncDrawerScale();
    window.addEventListener("resize", syncDrawerScale);
    return () => window.removeEventListener("resize", syncDrawerScale);
  }, [drawerOpen]);
  function sendMessage() {
    if (!draft.trim() && !files.length) {
      setInputError(true);
      return;
    }
    setInputError(false);
    send();
  }
  function attachFile(selected) {
    if (selected?.length) upload(selected);
  }
  function openDoc(doc) {
    setSearchOpen(false);
    setDetailFile(doc);
  }
  function updateScrollProgress() {
    const area = messageAreaRef.current;
    if (!area) return;
    const now = performance.now();
    const elapsed = Math.max(8, now - scrollSampleRef.current.time);
    const distance = area.scrollTop - scrollSampleRef.current.top;
    const scrollable = area.scrollHeight - area.clientHeight;
    const isAtBottom = scrollable - area.scrollTop <= 24;
    const velocity = distance / elapsed;
    const intensity = Math.min(7, Math.abs(velocity) * 2.3);
    const trail = Math.min(11, Math.abs(velocity) * 3.6) * (distance > 0 ? -1 : 1);
    scrollSampleRef.current = { time: now, top: area.scrollTop };
    if (scrollStopTimerRef.current) window.clearTimeout(scrollStopTimerRef.current);
    area.classList.toggle("at-bottom", isAtBottom);
    if (isAtBottom) {
      area.style.setProperty("--velocity-blur", "0px");
      area.style.setProperty("--velocity-trail", "0px");
      area.classList.remove("velocity-active");
    } else {
      area.style.setProperty("--velocity-blur", `${intensity}px`);
      area.style.setProperty("--velocity-trail", `${trail}px`);
      area.classList.add("velocity-active");
      scrollStopTimerRef.current = window.setTimeout(() => {
        area.style.setProperty("--velocity-blur", "0px");
        area.style.setProperty("--velocity-trail", "0px");
        area.classList.remove("velocity-active");
      }, 70);
    }
    setScrollProgress(scrollable > 0 ? area.scrollTop / scrollable : 0);
  }
  function toggleDrawer() {
    if (!drawerOpen) {
      const workspaceWidth = workspaceRef.current?.clientWidth || window.innerWidth;
      const drawerWidth = sidebarRef.current?.getBoundingClientRect().width || 240;
      const availableWidth = Math.max(0, workspaceWidth - drawerWidth - 14);
      setDrawerScale(Math.max(0.32, Math.min(0.94, availableWidth / workspaceWidth)));
    }
    setDrawerOpen((value) => !value);
  }
  return <main className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <button
    aria-label={drawerOpen ? "收起导航" : "展开导航"}
    className={`drawer-toggle ${drawerOpen ? "active" : ""}`}
    onClick={toggleDrawer}
    type="button"
  >
            <Icon name="menu" size={19} />
          </button>
          <Brand dark />
        </div>
        <div className="search-dock">
          <button className={`global-search ${searchOpen ? "active" : ""}`} onClick={() => setSearchOpen(true)} type="button">
            <Icon name="search" size={16} />
            <span>快速查找文档、图片与视频</span>
            <kbd>⌘ K</kbd>
          </button>
          <DocumentSearch docs={docs} open={searchOpen} onClose={() => setSearchOpen(false)} onSelect={openDoc} />
        </div>
        <button
    className="topbar-exit"
    onClick={(event) => setExitRect(event.currentTarget.getBoundingClientRect())}
    type="button"
  >
          <Icon name="logout" size={16} />
          <span>退出</span>
        </button>
      </header>

      <div
    className={`workspace ${drawerOpen ? "drawer-active" : ""}`}
    ref={workspaceRef}
    style={{ "--drawer-scale": drawerScale }}
  >
        <aside
    className={`sidebar drawer ${drawerOpen ? "open" : ""}`}
    onClick={(event) => event.stopPropagation()}
    ref={sidebarRef}
  >
          <div className="sidebar-title">
            <span>设备</span><small>手动传递</small>
          </div>
          <DeviceCard active={activeDevice === "phone"} detail="手动拉取 · Quantum App" icon="phone" name="Quantum App" onClick={(sourceRect) => {
    setActiveDevice("phone");
    setDetailFile({ kind: "device", meta: "iOS · 手动拉取", name: "Quantum App", sourceRect });
  }} />
          <DeviceCard active={activeDevice === "mac"} detail={devices.length ? "已配对 · 手动执行" : "点击配对飞书 Quantum"} icon="laptop" name="Mac Quantum" onClick={(sourceRect) => {
    setActiveDevice("mac");
    setDetailFile({ kind: "device", meta: devices.length ? "macOS · 已配对" : "macOS · 尚未配对", name: "Mac Quantum", description: "飞书：查看 / 拉取 / 执行 / 推送 QuanSyn", sourceRect, action: connectMac, actionLabel: "配对设备" });
  }} />

          <button className="sidebar-search" onClick={() => setSearchOpen(true)} type="button">
            <Icon name="search" size={17} />
            <span>快速查找</span>
            <kbd>⌘K</kbd>
          </button>

          <div className="sidebar-title recent-title">
            <span>最近传输</span>
            <button onClick={() => setSearchOpen(true)} type="button">查看全部</button>
          </div>
          {docs.slice(0, 3).map((doc, index) => <button className="recent-file" key={doc.name} onClick={(event) => setDetailFile({
    ...doc,
    kind: "file",
    sourceRect: event.currentTarget.getBoundingClientRect()
  })} type="button">
              <span className={`mini-file ${index ? "purple" : "blue"}`}><Icon name={doc.icon} size={17} /></span>
              <span><strong>{doc.name}</strong><small>{doc.meta.split(" · ").at(-1)}</small></span>
              <Icon name="chevron" size={14} />
            </button>)}

          <div className="sidebar-bottom">
            <div className="storage-head"><span>当前记录附件</span><strong>{(items.reduce((total, item) => total + item.files.reduce((sum, file) => sum + file.byte_size, 0), 0) / 1024 / 1024).toFixed(1)} MB</strong></div>
            {devices.map((device) => <div className="qs-device" key={device.id}><small>{device.sender_id}</small><button disabled={busy} onClick={() => revokeDevice(device.id)}>撤销</button></div>)}
          </div>
        </aside>

        <section
    className={`transfer-panel page-stage ${drawerOpen ? "shifted" : ""}`}
    onClick={() => {
      if (drawerOpen) setDrawerOpen(false);
    }}
  >
          <div className="chat-header">
            <div className="target-device">
              <span className="target-icon"><Icon name={activeDevice === "phone" ? "phone" : "laptop"} /></span>
              <div>
                <strong>{activeDevice === "phone" ? "Quantum App" : "Mac Quantum"}</strong>
                <small>手动拉取、执行和回传</small>
              </div>
            </div>
            <div className="chat-tools">
              <span><Icon name="shield" size={14} /> 账号私有</span>
              <button className="icon-button" aria-label="刷新记录" onClick={refresh} type="button"><Icon name="more" /></button>
            </div>
            <div className="chat-scroll-track" aria-hidden="true">
              <span style={{ transform: `scaleX(${scrollProgress})` }} />
            </div>
          </div>

          <div
    className="message-area"
    onScroll={updateScrollProgress}
    ref={messageAreaRef}
    style={{
      "--chat-shift-x": `${scrollProgress * 12}%`,
      "--chat-shift-y": `${scrollProgress * 32}%`
    }}
  >
            <div className="scroll-position" aria-hidden="true">
              <span style={{ transform: `scaleY(${scrollProgress})` }} />
            </div>
            {agreementContent || <>
            <div className="date-line"><span>传递记录</span></div>
            {loading && <p role="status">正在读取资料…</p>}
            {!loading && !messages.length && <div className="empty-result">从一条需求开始，完成的结果会回到这里。</div>}
            {messages.map((message) => <div className={`message-row ${message.direction === "request" ? "out" : "in"}`} key={message.id}>
                <div className="message-stack">
                  {message.direction === "request" && ["imported", "returned"].includes(message.status) && !message.text && !message.blocks.length && !message.files.length
                    ? <p>已导入 Quantum，服务器临时内容已清理</p>
                    : renderContent(message, setDetailFile)}
                  <small className="message-time">
                    {(/* @__PURE__ */ new Date(message.created_at + (/[Zz]|[+-]\d\d:\d\d$/.test(message.created_at) ? "" : "Z"))).toLocaleString("zh-CN", { hour12: false })}
                    <span className={`receipt ${message.status === "pending" ? "delivered" : "seen"}`}>
                      <span className="receipt-check">✓</span>
                      {message.status !== "pending" && <span className="receipt-check second">✓</span>}
                      <b>{{ pending: message.direction === "result" ? "已回传" : "已保存，待拉取", claimed: "正在拉取", imported: "已导入", returned: "已有结果" }[message.status]}</b>
                    </span>
                    <button className="text-button" disabled={busy} onClick={() => removeItem(message.id)}>删除</button>
                  </small>
                </div>
              </div>)}
            {next && <button className="text-button" disabled={busy} onClick={loadMore}>读取更早记录</button>}
            </>}

          </div>

          <div className="composer" onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
    event.preventDefault();
    attachFile(event.dataTransfer.files);
  }}>
            <div className={`compose-box ${inputError ? "input-error" : ""}`}>
              <textarea
    disabled={busy || !!agreementContent}
    aria-label="输入要传输的内容"
    onPaste={pasteImages}
    onChange={(event) => {
      setDraft(event.target.value);
      if (event.target.value.trim()) setInputError(false);
    }}
    onKeyDown={(event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
        event.preventDefault();
        sendMessage();
      }
    }}
    placeholder={`发送到 ${activeDevice === "phone" ? "Quantum App" : "Mac Quantum"}，支持粘贴图片或拖入文件`}
    value={draft}
  />
              <input
    className="hidden-input"
    onChange={(event) => {
      attachFile(event.target.files);
      event.target.value = "";
    }}
    ref={inputRef}
    multiple
    type="file"
  />
              {files.length > 0 && <div className="qs-selected">{files.map((file) => <span key={file.artifact_id}>{file.localPreview && <img className="qs-draft-image" src={file.localPreview} alt={file.metadata?.original_name || file.filename} />}{file.metadata?.original_name || file.filename}<button disabled={busy} aria-label="移除附件" onClick={() => removeFile(file.artifact_id)} type="button">×</button></span>)}</div>}
              <div className="compose-actions">
                <button disabled={busy} aria-label="添加附件" onClick={() => inputRef.current?.click()} type="button"><Icon name="paperclip" size={19} /></button>
                <span>{busy ? "正在传递…" : "Enter 发送"}</span>
                <button className="send-button" disabled={busy || !!agreementContent} aria-label="发送" onClick={sendMessage} type="button"><Icon name="send" size={18} /></button>
              </div>
            </div>
            <div className={`validation-message ${inputError || error ? "show" : ""}`} role="alert">
              {error || "请先输入需要发送的内容，或添加一个附件"}
            </div>
            <small className="drop-hint"><Icon name="shield" size={12} /> 资料按账号隔离 · 文件大小不限 · 最多 10 项</small>
          </div>
        </section>
      </div>

      {detailFile && createPortal(
    <DetailDialog file={detailFile} onClose={() => setDetailFile(null)} />,
    document.querySelector(".quansyn")
  )}
      {exitRect && createPortal(
    <ExitDialog onClosed={() => setExitRect(null)} onLogout={onLogout} sourceRect={exitRect} />,
    document.querySelector(".quansyn")
  )}
    </main>;
}
function OverlayAccessibility() {
  useEffect(() => {
    const root = document.querySelector(".quansyn");
    const observer = new MutationObserver(() => {
      root?.querySelectorAll(".insight-panel").forEach((panel) => {
        if (panel.getAttribute("role")) return;
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-modal", "true");
        panel.setAttribute("aria-label", panel.querySelector("h3")?.textContent || "详情");
        panel.querySelector("button")?.focus();
      });
    });
    observer.observe(root, { childList: true, subtree: true });
    function key(event) {
      const panel = root.querySelector(".insight-panel");
      if (!panel) return;
      if (event.key === "Escape") {
        panel.querySelector('button[aria-label="关闭详情"]')?.click();
      }
      if (event.key === "Tab") {
        const buttons = [...panel.querySelectorAll("button:not(:disabled), a[href], input")];
        const first = buttons[0], last = buttons.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", key);
    return () => {
      observer.disconnect();
      document.removeEventListener("keydown", key);
    };
  }, []);
  return null;
}
export {
  Brand,
  CodeDetail,
  CopyControl,
  DetailDialog,
  Icon,
  LoginPage,
  OverlayAccessibility,
  TransferView
};
