import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Brand, Icon, LoginPage, TransferView, CopyControl, CodeDetail, OverlayAccessibility } from "./QuanSynDesign.jsx";
import ReactMarkdown from "react-markdown";
import { Copy, X } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";
import { quansynApi } from "../../services/platformApi";
import { tableRows, plainContent } from "./content";
import "./design.css";
import "./quansyn.css";

const fileName = (file) => file.metadata?.original_name || file.filename;
const time = (value) => new Date(/[Zz]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString("zh-CN", { hour12: false });
function FileCard({ file, report, openDetail }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const image = /\.(png|jpe?g|webp|gif)$/i.test(fileName(file));
  useEffect(() => {
    if (!image) return;
    let active = true, objectUrl;
    quansynApi.file(file.artifact_id).then((blob) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(new Blob([blob], { type: /\.png$/i.test(fileName(file)) ? "image/png" : /\.webp$/i.test(fileName(file)) ? "image/webp" : /\.gif$/i.test(fileName(file)) ? "image/gif" : "image/jpeg" })); setUrl(objectUrl);
    }).catch((e) => active && report(e.message));
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [file.artifact_id, image, report]);
  async function download() {
    setBusy(true);
    try {
      const blob = await quansynApi.file(file.artifact_id);
      const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()))].map((x) => x.toString(16).padStart(2, "0")).join("");
      if (hash !== file.content_hash) throw new Error("文件校验失败，请重试");
      const link = document.createElement("a"); const objectUrl = URL.createObjectURL(blob);
      link.href = objectUrl; link.download = fileName(file); document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
    } catch (e) { report(e.message); } finally { setBusy(false); }
  }
  return <button disabled={busy} className={image ? "image-bubble" : "file-bubble"} onClick={(event) => openDetail({kind:"file", name:fileName(file), meta:`${(file.byte_size/1024).toFixed(1)} KB`, sourceRect:event.currentTarget.getBoundingClientRect(), action:download, actionLabel:"下载原件", description:"Quantum 账号私有附件", preview: image && url})} type="button">
    {image && <div className="image-preview">{url ? <img src={url} alt={fileName(file)} /> : <span>正在读取图片…</span>}</div>}
    <div className={image ? "file-meta" : "file-meta-inline"}><span className={`file-type ${image ? "image-type" : ""}`}><Icon name={image ? "image" : "file"} /></span><span><strong>{fileName(file)}</strong><small>{(file.byte_size/1024).toFixed(1)} KB</small></span><span className="open-file">{busy ? "正在下载…" : "预览"} <Icon name="chevron" size={14} /></span></div>
  </button>;
}

function CopyButton({ content, report }) {
  const [copied, setCopied] = useState(false);
  async function copy() { try { await navigator.clipboard.writeText(content); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { report("复制失败，请选中文字手动复制"); } }
  return <button className="qs-copy" aria-label="复制内容" onClick={copy}><Copy size={14} />{copied ? "已复制" : "复制"}</button>;
}
function PairDialog({ pair, close, report }) {
  const ref = useRef(null);
  useEffect(() => { ref.current.showModal(); }, []);
  return <dialog ref={ref} className="qs-modal" aria-labelledby="qs-pair-title" onCancel={close}><section><button aria-label="关闭配对" onClick={close}><X /></button><h2 id="qs-pair-title">连接 Mac Quantum</h2><p>在飞书向你的 Quantum 机器人发送下面这条指令。配对码 10 分钟内有效，只能使用一次。</p><pre>绑定 QuanSyn {pair.code}</pre><CopyButton content={`绑定 QuanSyn ${pair.code}`} report={report} /><p>绑定后可在导航中撤销设备权限。</p></section></dialog>;
}
function Table({ content }) {
  const [header, ...rows] = tableRows(content);
  return <table><thead><tr>{header.map((v, i) => <th key={i} scope="col">{v}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody></table>;
}
function Chart({ block, report }) {
  const [detail, setDetail] = useState(null);
  const maximum = Math.max(1, ...block.values.map(Math.abs));
  const rows = block.labels.map((label, index) => <div className="bar-row" key={index}><span>{label}</span><i><b style={{width:`${Math.abs(block.values[index])/maximum*100}%`}} /></i><strong>{block.values[index]}</strong></div>);
  return <><div className="mini-chart interactive-card" tabIndex={0} role="button" aria-label="查看图表详情" onClick={(event) => setDetail(event.currentTarget.getBoundingClientRect())} onKeyDown={(event) => { if(event.key === "Enter" || event.key === " ") { event.preventDefault(); setDetail(event.currentTarget.getBoundingClientRect()); } }}><div className="chart-title"><span>{block.content || "数据图表"}</span><small>{block.labels.length} 项</small></div>{rows}<span className="card-open-hint">点击查看详情 <Icon name="arrow" size={13} /></span></div>{detail && createPortal(<ChartDetail block={block} rect={detail} close={() => setDetail(null)} report={report} />,document.querySelector(".quansyn"))}</>;
}
function ChartDetail({block, rect, close, report}) {
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {const frame=requestAnimationFrame(() => setExpanded(true)); return () => cancelAnimationFrame(frame);},[]);
  function dismiss() {setExpanded(false);setTimeout(close,360);}
  const max=Math.max(1,...block.values.map(Math.abs));
  return <div className={`insight-overlay ${expanded ? "expanded" : ""}`} onMouseDown={dismiss}><section className="insight-panel" style={{"--source-left":`${rect.left}px`,"--source-top":`${rect.top}px`,"--source-width":`${rect.width}px`,"--source-height":`${rect.height}px`}} onMouseDown={(event) => event.stopPropagation()}><header><div><span>数据洞察</span><h3>{block.content || "数据图表"}</h3></div><button aria-label="关闭详情" onClick={dismiss}>×</button></header><div className="detail-chart">{block.labels.map((label,index) => <div className="detail-bar" key={index}><span>{label}</span><i><b style={{width:`${Math.abs(block.values[index])/max*100}%`}} /></i><strong>{block.values[index]}</strong></div>)}</div><footer><span>此次返回的实际数值</span><CopyControl content={block.labels.map((label,index) => `${label}\t${block.values[index]}`).join("\n")} report={report} /></footer></section></div>;
}
function Code({content, report}) {
  const [rect,setRect]=useState(null);
  const code=content.replace(/^```[^\n]*\n/,"").replace(/\n```$/,"");
  return <><div className="code-block expandable-code" tabIndex={0} role="button" aria-label="查看代码详情" onClick={(event) => setRect(event.currentTarget.getBoundingClientRect())} onKeyDown={(event) => {if(event.key === "Enter" || event.key === " "){event.preventDefault();setRect(event.currentTarget.getBoundingClientRect());}}}><div><span><i/><i/><i/></span><small>代码</small><CopyControl className="code-copy" content={code} report={report}/></div><code>{code}</code></div>{rect && createPortal(<CodeDetail code={code} onClosed={() => setRect(null)} sourceRect={rect}/>,document.querySelector(".quansyn"))}</>;
}
function Content({item, report, openDetail}) {
  const markdown = (content) => <ReactMarkdown skipHtml components={{img:({alt}) => <span>{alt || "图片请通过附件查看"}</span>, pre:({children}) => children, code:({children,className}) => String(children).includes("\n") || className?.startsWith("language-") ? <Code content={String(children)} report={report}/> : <code className={className}>{children}</code>}}>{content}</ReactMarkdown>;
  return <>
    {item.direction === "request" ? item.text && <div className="text-bubble">{item.text}</div> : <article className="rich-answer"><CopyControl content={plainContent(item)} report={report}/><div className="assistant-label"><span><img src="/quansyn/logo.png" alt=""/></span> QuanSyn · Quantum</div>{item.text && markdown(item.text)}{item.blocks.map((block,index) => <section key={index}>{block.kind === "chart" ? <Chart block={block} report={report}/> : block.kind === "table" ? <div className="qs-table"><Table content={block.content}/><CopyControl content={block.content} report={report}/></div> : block.kind === "code" ? <Code content={block.content} report={report}/> : markdown(block.content)}</section>)}</article>}
    {item.direction === "request" && item.blocks.length > 0 && <article className="rich-answer">{item.blocks.map((block,index) => <section key={index}>{block.kind === "chart" ? <Chart block={block} report={report}/> : block.kind === "table" ? <Table content={block.content}/> : block.kind === "code" ? <Code content={block.content} report={report}/> : markdown(block.content)}</section>)}</article>}
    {item.files.map((file) => <FileCard key={file.artifact_id} file={file} report={report} openDetail={openDetail}/>)}
  </>;
}

export default function QuanSynPage() {
  const { isAuthenticated, isReady, logout, sessionScopeKey } = useAuth();
  const [items, setItems] = useState([]), [files, setFiles] = useState([]), [devices, setDevices] = useState([]);
  const [draft, setDraft] = useState(""), [target, setTarget] = useState("ios");
  const [error, setError] = useState(""), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false);
  const [pair, setPair] = useState(null), [agreement, setAgreement] = useState(null);
  const [next, setNext] = useState(null);
  const requestKey = useRef(crypto.randomUUID()), generation = useRef(0), paged = useRef(false);
  useEffect(() => { const old = document.title; document.title = "QuanSyn · Quantum"; return () => { document.title = old; }; }, []);
  const report = useCallback((message) => setError(message), []);
  const refresh = useCallback(async () => {
    const epoch = generation.current;
    try {
      const [list, deviceList] = await Promise.all([quansynApi.list(), quansynApi.devices()]);
      if (epoch !== generation.current) return;
      setItems((current) => paged.current ? [...list.items, ...current.filter((item) => !list.items.some((fresh) => fresh.id === item.id))] : list.items); if (!paged.current) setNext(list.next); setDevices(deviceList.items); setAgreement(null);
    } catch (e) {
      if (epoch !== generation.current) return;
      if (e.status === 401) logout();
      else if (e.status === 428) { try { setAgreement(await quansynApi.agreement()); } catch (a) { setError(a.message); } }
      else setError(e.message);
    } finally { if (epoch === generation.current) setLoading(false); }
  }, [isAuthenticated, sessionScopeKey]);
  useEffect(() => {
    generation.current += 1; paged.current = false; setDevices([]); setNext(null); setAgreement(null); setBusy(false); setItems([]); setFiles([]); setPair(null); setDraft(""); setLoading(true);
    if (!isAuthenticated) return;
    refresh(); const timer = setInterval(refresh, 5000); return () => { generation.current += 1; clearInterval(timer); };
  }, [isAuthenticated, sessionScopeKey, refresh]);
  async function action(fn) { if (busy) return; const epoch = generation.current; setBusy(true); setError(""); try { await fn(epoch); } catch (e) { if (epoch === generation.current) setError(e.message); } finally { if (epoch === generation.current) setBusy(false); } }
  async function upload(selected) {
    const chosen = [...selected]; if (chosen.length + files.length > 10) { setError("最多添加 10 个附件"); return; }
    await action(async (epoch) => { for (const file of chosen) { if (file.size > 25 * 1024 * 1024) throw new Error(`${file.name} 超过 25 MB`); const receipt = await quansynApi.upload(file); if (epoch !== generation.current) return; requestKey.current = crypto.randomUUID(); setFiles((current) => [...current, receipt]); } });
  }
  async function send() {
    if (!draft.trim() && !files.length) return;
    await action(async (epoch) => {
      await quansynApi.send({ request_id: requestKey.current, target, text: draft, files: files.map((file) => ({ artifact_id: file.artifact_id })) });
      if (epoch !== generation.current) return;
      setDraft(""); setFiles([]); requestKey.current = crypto.randomUUID(); await refresh();
    });
  }
  if (!isReady) return <div className="quansyn qs-loading" role="status">正在恢复账号…</div>;
  if (!isAuthenticated) return <div className="quansyn"><OverlayAccessibility /><LoginPage error={error} report={report} /></div>;
  return <div className="quansyn"><OverlayAccessibility /><TransferView items={items} files={files} devices={devices} draft={draft} setDraft={(value) => {setDraft(value);requestKey.current=crypto.randomUUID();}} target={target} setTarget={(value) => {setTarget(value);requestKey.current=crypto.randomUUID();}} busy={busy} loading={loading} error={error} send={send} upload={upload} onLogout={logout}
    refresh={() => {setError("");refresh();}}
    removeFile={(id) => {setFiles(files.filter((file) => file.artifact_id !== id));requestKey.current=crypto.randomUUID();}}
    removeItem={(id) => action(async () => {await quansynApi.remove(id);await refresh();})}
    next={next} loadMore={() => action(async () => {const epoch=generation.current;const page=await quansynApi.list(`?before=${encodeURIComponent(next)}`);if(epoch !== generation.current)return;paged.current=true;setItems((current) => [...current,...page.items]);setNext(page.next);})}
    connectMac={() => action(async (epoch) => {const value=await quansynApi.pair();if(epoch === generation.current)setPair(value);})}
    revokeDevice={(id) => action(async () => {await quansynApi.revoke(id);await refresh();})}
    renderContent={(item,openDetail) => <Content item={item} report={report} openDetail={openDetail}/>}
    openFile={async (file) => {try{const blob=await quansynApi.file(file.artifact_id);const hash=[...new Uint8Array(await crypto.subtle.digest("SHA-256",await blob.arrayBuffer()))].map((value) => value.toString(16).padStart(2,"0")).join("");if(hash !== file.content_hash)throw new Error("文件校验失败，请重试");const link=document.createElement("a"),url=URL.createObjectURL(blob);link.href=url;link.download=fileName(file);document.body.append(link);link.click();link.remove();setTimeout(() => URL.revokeObjectURL(url),30000);}catch(error){report(error.message);}}}
    agreementContent={agreement && <section className="qs-agreement"><h2>{agreement.title}</h2>{agreement.sections.map((section) => <section key={section.id}><h3>{section.title}</h3>{section.clauses.map((clause,index) => <p key={index}>{clause}</p>)}</section>)}<button disabled={busy} className="primary-button" onClick={() => action(async () => {await quansynApi.accept(agreement.version);await refresh();})}>我已阅读并同意，继续使用</button></section>}
  />{pair && <PairDialog pair={pair} close={() => setPair(null)} report={report}/>}</div>;
}
