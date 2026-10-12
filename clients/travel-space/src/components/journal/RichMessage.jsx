import React from 'react';
// React escapes all text. Only these formatting tokens are interpreted; raw HTML is text.
import {safeLink,safeImage,safeAudio} from './journal-media';
export {safeLink,safeImage,safeAudio} from './journal-media';
function Inline({text}){const tokens=String(text).split(/(\*\*[^*\n]+\*\*|`[^`\n]+`|~~[^~\n]+~~|\*[^*\n]+\*|\[[^\]\n]+\]\([^\s)]+\))/g);return tokens.map((t,i)=>t.startsWith('**')&&t.endsWith('**')?<strong key={i}>{t.slice(2,-2)}</strong>:t.startsWith('`')&&t.endsWith('`')?<code key={i}>{t.slice(1,-1)}</code>:t.startsWith('~~')&&t.endsWith('~~')?<del key={i}>{t.slice(2,-2)}</del>:t.startsWith('*')&&t.endsWith('*')?<em key={i}>{t.slice(1,-1)}</em>:t.startsWith('[')?(()=>{const m=t.match(/^\[([^\]]+)\]\(([^)]+)\)$/),href=m&&safeLink(m[2]);return href?<a key={i} href={href} target="_blank" rel="noreferrer">{m[1]}</a>:t;})():t);}
export function richBlocks(text){
 const lines=String(text||'').slice(0,20000).split('\n'),blocks=[];let i=0;
 while(i<lines.length){const line=lines[i];if(!line.trim()){i++;continue;}
  if(line.startsWith('```')){const lang=line.slice(3).trim();i++;const body=[];while(i<lines.length&&!lines[i].startsWith('```'))body.push(lines[i++]);if(i<lines.length)i++;blocks.push({type:lang==='card'?'card':'code',lang,text:body.join('\n')});continue;}
  if(line.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])){const cells=x=>x.trim().replace(/^\||\|$/g,'').split('|').map(x=>x.trim()).slice(0,10);const heads=cells(line);i+=2;const rows=[];while(i<lines.length&&lines[i].includes('|')&&lines[i].trim())rows.push(cells(lines[i++]));blocks.push({type:'table',heads,rows:rows.slice(0,30)});continue;}
  const heading=line.match(/^(#{1,3})\s+(.+)/);if(heading){blocks.push({type:'heading',level:heading[1].length,text:heading[2]});i++;continue;}
  if(/^[-*]\s+/.test(line)){const items=[];while(i<lines.length&&/^[-*]\s+/.test(lines[i]))items.push(lines[i++].slice(2));blocks.push({type:'list',items});continue;}
  if(/^>\s?/.test(line)){blocks.push({type:'quote',text:line.replace(/^>\s?/, '')});i++;continue;}
  blocks.push({type:'paragraph',text:line});i++;
 }return blocks;
}
export default function RichMessage({text,attachments=[]}){let priorHeading=2;return <div className="rich-message">{attachments.filter(x=>x.kind==='image'&&safeImage(x.src)).map((x,i)=><figure key={i}><img src={x.src} alt={x.name||'对话附图'}/></figure>)}{richBlocks(text).map((b,i)=>b.type==='code'?<pre key={i}><small>{b.lang||'代码'}</small><code>{b.text}</code></pre>:b.type==='card'?<aside className="rich-glass-card glass" key={i}><RichMessage text={b.text}/></aside>:b.type==='table'?<div className="rich-table-scroll" key={i}><table><thead><tr>{b.heads.map((h,j)=><th scope="col" key={j}><Inline text={h}/></th>)}</tr></thead><tbody>{b.rows.map((row,j)=><tr key={j}>{b.heads.map((_,k)=><td key={k}><Inline text={row[k]||''}/></td>)}</tr>)}</tbody></table></div>:b.type==='heading'?React.createElement('h'+(priorHeading=Math.min(5,b.level+2,priorHeading+1)),{key:i},<Inline text={b.text}/>):b.type==='list'?<ul key={i}>{b.items.map((x,j)=><li key={j}><Inline text={x}/></li>)}</ul>:b.type==='quote'?<blockquote key={i}><Inline text={b.text}/></blockquote>:<p key={i}><Inline text={b.text}/></p>)}</div>;}
