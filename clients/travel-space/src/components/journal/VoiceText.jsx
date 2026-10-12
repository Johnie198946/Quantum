import {invoke} from '../../production/bridge';
import FloatingField from '../FloatingField';
import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {motion,useReducedMotion} from 'motion/react';
import {Glass,Icon,spring} from '../UI';
import './VoiceText.css';
const FORMATS=[['bold','粗体','B'],['italic','斜体','I'],['code','代码块','</>'],['table','表格','▦'],['card','毛玻璃卡片','◇']];
const LONG_PRESS_MS=550;

// Native textareas expose character ranges but not their painted rectangles.
// A temporary, invisible mirror supplies only the caret's position; editing
// and selection continue to belong to the real textarea.
function caretBounds(control,index){
 const style=getComputedStyle(control),mirror=document.createElement('div'),marker=document.createElement('span');
 for(const property of ['fontFamily','fontSize','fontWeight','fontStyle','letterSpacing','lineHeight','textAlign','textIndent','paddingTop','paddingRight','paddingBottom','paddingLeft','borderTopWidth','borderRightWidth','borderBottomWidth','borderLeftWidth','boxSizing','wordBreak','overflowWrap','tabSize'])mirror.style[property]=style[property];
 Object.assign(mirror.style,{position:'fixed',left:'0',top:'0',width:control.offsetWidth+'px',height:'auto',minHeight:'0',whiteSpace:'pre-wrap',visibility:'hidden',pointerEvents:'none',overflow:'hidden'});
 mirror.append(document.createTextNode(control.value.slice(0,index)));marker.textContent=control.value[index]||'\u200b';mirror.append(marker);document.body.append(mirror);
 const rect=control.getBoundingClientRect(),point=marker.getBoundingClientRect(),origin=mirror.getBoundingClientRect(),scaleX=rect.width/(control.offsetWidth||rect.width),scaleY=rect.height/(control.offsetHeight||rect.height);
 const result={left:rect.left+(point.left-origin.left-control.scrollLeft)*scaleX,top:rect.top+(point.top-origin.top-control.scrollTop)*scaleY,bottom:rect.top+(point.bottom-origin.top-control.scrollTop)*scaleY};
 mirror.remove();return result;
}
function visibleBounds(control){
 const viewport=window.visualViewport;
 const bounds={left:viewport?.offsetLeft||0,top:viewport?.offsetTop||0,right:(viewport?.offsetLeft||0)+(viewport?.width||window.innerWidth),bottom:(viewport?.offsetTop||0)+(viewport?.height||window.innerHeight)};
 for(let parent=control.parentElement;parent;parent=parent.parentElement){
  const style=getComputedStyle(parent),rect=parent.getBoundingClientRect();
  if(parent.classList.contains('phone')||/(auto|scroll|hidden|clip)/.test(style.overflowX)){bounds.left=Math.max(bounds.left,rect.left);bounds.right=Math.min(bounds.right,rect.right);}
  if(parent.classList.contains('phone')||/(auto|scroll|hidden|clip)/.test(style.overflowY)){bounds.top=Math.max(bounds.top,rect.top);bounds.bottom=Math.min(bounds.bottom,rect.bottom);}
 }
 return bounds;
}
export const MEDIA_LIMIT=900000;
export async function readMedia(file){
 if(!/^image\/(jpeg|png|webp)$|^audio\/(wav|mp4|m4a|webm|ogg)$/i.test(file.type))throw new Error('请选择 JPG、PNG、WebP 图片或常用录音格式。');
 let upload=file;
 if(file.type.startsWith('image/')&&file.size>MEDIA_LIMIT){
  if(file.size>12*1024*1024)throw new Error('请选择小于12 MB的照片。');
  const url=URL.createObjectURL(file);
  try{const image=new Image();image.src=url;await image.decode();const ratio=Math.min(1,1600/Math.max(image.naturalWidth,image.naturalHeight));
   const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*ratio));canvas.height=Math.max(1,Math.round(image.naturalHeight*ratio));
   canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);upload=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.78));
   if(!upload)throw new Error('照片未能整理，请重新选择。');
  }finally{URL.revokeObjectURL(url);}
 }
 if(upload.size>MEDIA_LIMIT)throw new Error('请缩小图片，或选择小于900 KB的录音。');
 const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('未能读取附件'));reader.readAsDataURL(upload);});
 const result=await invoke('uploadMedia',{data});return result.src;
}

export default function VoiceText({value,onChange,label='自己的旅行记录',placeholder='今天遇见了什么？',rows=3,onListeningChange,onSubmit,onMedia,rich=false}){
 const [listening,setListening]=useState(false),[status,setStatus]=useState(''),[interim,setInterim]=useState(''),[levels,setLevels]=useState(Array(20).fill(0)),[saved,setSaved]=useState(false),[finalizing,setFinalizing]=useState(false),[speechFinalizing,setSpeechFinalizing]=useState(false);
 const input=useRef(null),session=useRef(null),alive=useRef(true),hold=useRef(false),ignoreClick=useRef(false),timer=useRef(null),file=useRef(null),valueRef=useRef(value),changeRef=useRef(onChange),mediaRef=useRef(onMedia),reduced=useReducedMotion();valueRef.current=value;changeRef.current=onChange;mediaRef.current=onMedia;
 const [fieldHost,setFieldHost]=useState(null),[toolsOpen,setToolsOpen]=useState(false),[toolPosition,setToolPosition]=useState({left:8,top:0,placement:'above'}),[toolIndex,setToolIndex]=useState(0),[toolRange,setToolRange]=useState({start:0,end:0,trigger:'selection'});
 const frame=useRef(null),tools=useRef(null),toolButtons=useRef([]),selection=useRef({start:0,end:0,direction:'none'}),press=useRef(null),pressTimer=useRef(null),selectionFrame=useRef(null),toolFocus=useRef(false),dismissedRange=useRef(''),forcedRange=useRef({key:'',trigger:''}),selectionTrigger=useRef('selection'),openRef=useRef(false),readOnlyRef=useRef(false);
 openRef.current=toolsOpen;readOnlyRef.current=listening||saved;
 useLayoutEffect(()=>{setFieldHost(input.current?.closest('.floating-field')||null);},[]);
 useEffect(()=>{onListeningChange?.(listening||finalizing||speechFinalizing);},[listening,finalizing,speechFinalizing,onListeningChange]);
 useLayoutEffect(()=>{const f=input.current;if(f){f.style.height='auto';f.style.height=Math.min(260,Math.max(128,f.scrollHeight))+'px';}},[value]);
 function cancelLongPress(){clearTimeout(pressTimer.current);press.current=null;}
 function dismissTools(){dismissedRange.current=selection.current.start+':'+selection.current.end;forcedRange.current={key:'',trigger:''};setToolsOpen(false);toolFocus.current=false;}
 function placeTools(){
  const f=input.current,wrapper=frame.current;if(!f||!wrapper||!openRef.current)return;
  const bounds=visibleBounds(f),rect=wrapper.getBoundingClientRect(),scaleX=rect.width/(wrapper.offsetWidth||rect.width),scaleY=rect.height/(wrapper.offsetHeight||rect.height),anchor=caretBounds(f,selection.current.direction==='backward'?selection.current.start:selection.current.end);
  const surface=tools.current?.parentElement,width=(surface?.offsetWidth||236)*scaleX,height=(surface?.offsetHeight||52)*scaleY,pad=6;
  if(bounds.right-bounds.left<width+pad*2||bounds.bottom-bounds.top<height+pad*2||anchor.bottom<bounds.top||anchor.top>bounds.bottom){setToolsOpen(false);return;}
  const left=Math.max(bounds.left+pad,Math.min(anchor.left-width/2,bounds.right-width-pad));
  const above=anchor.top-height-8*scaleY,placement=above>=bounds.top+pad?'above':'below';
  const top=Math.max(bounds.top+pad,Math.min(placement==='above'?above:anchor.bottom+8*scaleY,bounds.bottom-height-pad));
  setToolPosition(prev=>{const next={left:(left-rect.left)/scaleX,top:(top-rect.top)/scaleY,placement};return Math.abs(prev.left-next.left)<.5&&Math.abs(prev.top-next.top)<.5&&prev.placement===placement?prev:next;});
 }
 function captureSelection(force=false,trigger=selectionTrigger.current){
  const f=input.current;if(!rich||!f||readOnlyRef.current||document.activeElement!==f)return;
  const start=f.selectionStart,end=f.selectionEnd,key=start+':'+end;selection.current={start,end,direction:f.selectionDirection||'none'};
  if(!force&&dismissedRange.current===key)return;
  if(force)forcedRange.current={key,trigger};
  const forced=forcedRange.current.key===key;
  if(start===end&&!force&&!forced){setToolsOpen(false);return;}
  dismissedRange.current='';setToolRange({start,end,trigger:forced?forcedRange.current.trigger:trigger});setToolsOpen(true);
 }
 function selectAtCaret(){
  const f=input.current;if(!f)return;
  if(f.selectionStart===f.selectionEnd&&f.value){
   let start=f.selectionStart,end=start;
   if(typeof Intl.Segmenter==='function'){
    const caret=Math.min(start,f.value.length-1),segments=new Intl.Segmenter('zh',{granularity:'word'}).segment(f.value);
    for(const segment of segments){if(caret>=segment.index&&caret<segment.index+segment.segment.length){start=segment.index;end=start+segment.segment.length;break;}}
   }else{
    const isWord=character=>!!character&&/[\p{L}\p{N}_]/u.test(character);
    while(start>0&&isWord(f.value[start-1]))start--;while(end<f.value.length&&isWord(f.value[end]))end++;
    if(start===end){start=Math.max(0,Math.min(start,f.value.length-1));if(/[\uDC00-\uDFFF]/.test(f.value[start])&&start>0)start--;end=start+(f.value.codePointAt(start)>0xFFFF?2:1);}
   }
   f.setSelectionRange(start,end);
  }
 }
 function beginSelectionPress(event){
  if(!rich||readOnlyRef.current||event.button!==0)return;
  cancelLongPress();dismissedRange.current='';forcedRange.current={key:'',trigger:''};selectionTrigger.current='selection';press.current={x:event.clientX,y:event.clientY};
  pressTimer.current=setTimeout(()=>{press.current=null;if(document.activeElement!==input.current)return;selectAtCaret();captureSelection(true,'longpress');},LONG_PRESS_MS);
 }
 function moveSelectionPress(x,y){if(press.current&&Math.hypot(x-press.current.x,y-press.current.y)>10)cancelLongPress();}
 function selectionSoon(){cancelAnimationFrame(selectionFrame.current);selectionFrame.current=requestAnimationFrame(()=>captureSelection());}
 function editorKeyDown(event){
  if(!rich)return;
  if(event.key==='Escape'&&openRef.current){event.preventDefault();event.stopPropagation();dismissTools();return;}
  if((event.shiftKey&&event.key==='F10')||event.key==='ContextMenu'){event.preventDefault();dismissedRange.current='';toolFocus.current=true;captureSelection(true,'keyboard');return;}
  if(event.shiftKey||((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='a')){dismissedRange.current='';selectionTrigger.current='keyboard';}
 }
 function toolbarKeyDown(event,index){
  if(event.key==='Escape'){event.preventDefault();event.stopPropagation();dismissTools();input.current?.focus({preventScroll:true});return;}
  const next=event.key==='ArrowRight'?(index+1)%FORMATS.length:event.key==='ArrowLeft'?(index+FORMATS.length-1)%FORMATS.length:event.key==='Home'?0:event.key==='End'?FORMATS.length-1:null;
  if(next!==null){event.preventDefault();setToolIndex(next);toolButtons.current[next]?.focus({preventScroll:true});}
 }
 useEffect(()=>{
  if(!rich)return;
  const update=()=>captureSelection(),reposition=()=>placeTools(),outside=event=>{if(!frame.current?.contains(event.target)){cancelLongPress();dismissTools();}},blur=()=>{cancelLongPress();dismissTools();};
  document.addEventListener('selectionchange',update);document.addEventListener('pointerdown',outside,true);document.addEventListener('scroll',reposition,true);window.addEventListener('blur',blur);window.addEventListener('resize',reposition);window.visualViewport?.addEventListener('resize',reposition);window.visualViewport?.addEventListener('scroll',reposition);
  const observer=new ResizeObserver(reposition);if(frame.current)observer.observe(frame.current);
  return()=>{document.removeEventListener('selectionchange',update);document.removeEventListener('pointerdown',outside,true);document.removeEventListener('scroll',reposition,true);window.removeEventListener('blur',blur);window.removeEventListener('resize',reposition);window.visualViewport?.removeEventListener('resize',reposition);window.visualViewport?.removeEventListener('scroll',reposition);observer.disconnect();cancelLongPress();cancelAnimationFrame(selectionFrame.current);};
 },[rich]);
 useLayoutEffect(()=>{if(toolsOpen){placeTools();if(toolFocus.current){toolFocus.current=false;toolButtons.current[toolIndex]?.focus({preventScroll:true});}}},[toolsOpen,toolRange,value]);
 useEffect(()=>{if(listening||saved){cancelLongPress();dismissTools();}},[listening,saved]);
 function stop(cancel=false){const s=session.current;hold.current=false;if(!s||(s.released&&!cancel))return;s.released=true;s.cancelled=cancel;if(s.native){clearInterval(s.poll);invoke('voiceStop',{cancel}).catch(()=>{});if(alive.current){setListening(false);setSpeechFinalizing(!cancel);setLevels(Array(20).fill(0));}return;}cancelAnimationFrame(s.raf);clearTimeout(s.speechTimer);if(s.recognition){if(!cancel&&!s.recognitionEnded&&alive.current){setSpeechFinalizing(true);s.speechTimer=setTimeout(()=>{s.recognition.onresult=null;s.recognition.onend=null;s.recognition.onerror=null;try{s.recognition.abort();}catch{}if(alive.current){setSpeechFinalizing(false);setInterim('');setStatus('转写暂未完成，可以继续输入；已有文字与录音已保留。');}},4000);}try{cancel?s.recognition.abort():s.recognition.stop();}catch{if(alive.current)setSpeechFinalizing(false);}}if(s.recorder?.state==='recording'){if(alive.current&&!cancel)setFinalizing(true);s.recorder.stop();}s.stream?.getTracks().forEach(t=>t.stop());s.context?.close().catch(()=>{});clearTimeout(s.limit);if(alive.current){setListening(false);setLevels(Array(20).fill(0));if(cancel){setInterim('');setSpeechFinalizing(false);setFinalizing(false);}}}
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;clearTimeout(timer.current);stop(true);};},[]);
 function recognize(s){const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition)return;const r=new Recognition();s.recognition=r;s.final='';r.lang='zh-CN';r.continuous=true;r.interimResults=true;r.onresult=e=>{if(!alive.current||s.cancelled||session.current!==s)return;let final='',partial='';for(let i=0;i<e.results.length;i++){const result=e.results[i];if(result.isFinal)final+=result[0].transcript;else partial+=result[0].transcript;}if(final&&final!==s.final){const delta=final.startsWith(s.final)?final.slice(s.final.length):final;s.final=final;s.hasWords=true;changeRef.current([valueRef.current.trimEnd(),delta].filter(Boolean).join('\n'));}setInterim(partial);};r.onerror=e=>{if(!alive.current||s.cancelled||session.current!==s)return;s.recognitionEnded=true;clearTimeout(s.speechTimer);setSpeechFinalizing(false);setStatus(e.error==='not-allowed'?'语音识别未获允许，仍可输入文字。':'语音转写暂时不可用，仍可保留录音或输入文字。');};r.onend=()=>{s.recognitionEnded=true;clearTimeout(s.speechTimer);if(alive.current&&session.current===s){setSpeechFinalizing(false);setInterim('');if(s.released&&s.hasWords)setStatus('文字已插入输入框。');}};try{r.start();}catch{s.recognitionEnded=true;setStatus('语音转写暂时无法启动，可以继续输入。');}}
 async function start(){if(listening||finalizing||speechFinalizing||saved)return;const s={released:false,cancelled:false,wave:[],chunks:[],started:Date.now()};session.current=s;hold.current=true;setListening(true);setStatus('');setInterim('');if(!navigator.mediaDevices?.getUserMedia){setStatus('此浏览器无法录音，请直接输入文字。');stop(true);input.current?.focus();return;}
  if(window.webkit?.messageHandlers?.quantum){
   s.native=true;setListening(true);setStatus('正在聆听…');
   s.poll=setInterval(()=>invoke('voiceStatus').then(v=>{if(alive.current&&!s.cancelled){setInterim(v.text||'');setLevels(v.levels||[]);}}).catch(()=>{}),200);
   try{const result=await invoke('voice',{capture:!!mediaRef.current});if(alive.current&&!s.cancelled){if(result.text)changeRef.current([valueRef.current.trimEnd(),result.text].filter(Boolean).join('\n'));if(result.media)mediaRef.current?.(result.media);setStatus('原话已留下，请确认后保存。');}}
   catch(error){if(alive.current&&!s.cancelled)setStatus(error.message||String(error));}
   finally{clearInterval(s.poll);if(alive.current){setListening(false);setSpeechFinalizing(false);setInterim('');setLevels(Array(20).fill(0));}}return;
  }
  try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});if(s.released||!alive.current){stream.getTracks().forEach(t=>t.stop());return;}s.stream=stream;s.started=Date.now();const AC=window.AudioContext||window.webkitAudioContext;if(AC){s.context=new AC();await s.context.resume();if(s.released||!alive.current){stream.getTracks().forEach(t=>t.stop());return;}const analyser=s.context.createAnalyser();analyser.fftSize=256;s.context.createMediaStreamSource(stream).connect(analyser);const bins=new Uint8Array(analyser.frequencyBinCount);let last=0;const sample=now=>{if(s.released||!alive.current)return;analyser.getByteFrequencyData(bins);if(now-last>45){const bars=Array.from({length:20},(_,i)=>Math.max(...bins.slice(Math.floor(i*bins.length/20),Math.max(1,Math.floor((i+1)*bins.length/20))))/255);setLevels(bars);s.wave.push(Math.max(...bars));last=now;}s.raf=requestAnimationFrame(sample);};s.raf=requestAnimationFrame(sample);}
   if(mediaRef.current&&window.MediaRecorder){s.recorder=new MediaRecorder(stream);s.recorder.ondataavailable=e=>{if(e.data.size)s.chunks.push(e.data);};s.recorder.onstop=async()=>{if(s.cancelled||!alive.current)return;try{const blob=new Blob(s.chunks,{type:s.recorder.mimeType||'audio/webm'});if(blob.size&&Date.now()-s.started>250){const src=await readMedia(blob);if(!alive.current||s.cancelled)return;const wave=Array.from({length:24},(_,i)=>{const a=Math.floor(i*s.wave.length/24),b=Math.max(a+1,Math.floor((i+1)*s.wave.length/24)),slice=s.wave.slice(a,b);return slice.length?slice.reduce((x,y)=>x+y,0)/slice.length:0;});mediaRef.current({kind:'audio',src,seconds:Math.min(45,(Date.now()-s.started)/1000),wave,name:'旅行录音'});}}catch(e){if(alive.current)setStatus(e.message);}finally{if(alive.current)setFinalizing(false);}};s.recorder.start();}
   recognize(s);if(!s.recognition)setStatus(onMedia?'语音转写不受此浏览器支持；录音会保留，文字可直接输入。':'语音转写不受此浏览器支持，请直接输入。');s.limit=setTimeout(()=>{stop();if(alive.current)setStatus('录音已在45秒处结束。');},45000);
  }catch{if(alive.current&&!s.released){setStatus('麦克风未获允许或不可用，原文字已保留。');stop(true);}}
 }
 function format(kind){
  const f=input.current;if(!f||readOnlyRef.current)return;
  const text=String(valueRef.current??''),a=Math.min(selection.current.start,text.length),b=Math.min(selection.current.end,text.length),selected=text.slice(a,b)||'文字',scrollTop=f.scrollTop;
  const insert={bold:'**'+selected+'**',italic:'*'+selected+'*',code:'\n```text\n'+selected+'\n```\n',table:'\n| 安排 | 时间 |\n| --- | --- |\n| 自由停留 | 16:00 |\n',card:'\n```card\n**沿途小记**\n'+selected+'\n```\n'}[kind];
  dismissTools();changeRef.current(text.slice(0,a)+insert+text.slice(b));
  requestAnimationFrame(()=>{if(!alive.current||!f.isConnected)return;const caret=a+insert.length;selection.current={start:caret,end:caret,direction:'none'};f.focus({preventScroll:true});f.setSelectionRange(caret,caret);f.scrollTop=scrollTop;});
 }
 async function attach(e){const f=e.target.files?.[0];e.target.value='';if(!f)return;if(!['image/png','image/jpeg','image/webp','image/gif'].includes(f.type)){setStatus('请选择 PNG、JPEG、WebP 或 GIF 图片。');return;}try{const src=await readMedia(f);if(!alive.current)return;mediaRef.current({kind:'image',src,name:f.name});setStatus('图片已加入草稿。');}catch(e){setStatus(e.message);}}
 async function submit(){if(saved||listening||finalizing||speechFinalizing)return;const result=await onSubmit?.();if(result){setStatus(result);return;}setSaved(true);}
 const actions=<div className="voice-actions voice-frame-actions" role="group" aria-label="记录输入操作" style={{'--voice-reserved-space':((onMedia?48:0)+(onSubmit?48:0))+'px'}}>
  <motion.button type="button" className={'voice-hold'+(listening?' is-listening':'')} aria-label={listening?'松手结束录音':'语音插入转文字'} aria-pressed={listening} disabled={saved||finalizing||speechFinalizing} animate={{width:listening?240:40}} transition={reduced?{duration:0}:{type:'spring',stiffness:350,damping:26}} onPointerDown={e=>{if(e.button!==0)return;ignoreClick.current=true;e.currentTarget.setPointerCapture(e.pointerId);start();}} onPointerUp={()=>stop()} onPointerCancel={()=>stop(true)} onLostPointerCapture={()=>{if(hold.current)stop();}} onKeyDown={e=>{if([' ','Enter'].includes(e.key)&&!e.repeat){e.preventDefault();ignoreClick.current=true;start();}}} onKeyUp={e=>{if([' ','Enter'].includes(e.key)){e.preventDefault();stop();ignoreClick.current=false;}}} onClick={e=>{if(ignoreClick.current){ignoreClick.current=false;return;}if(e.detail===0)listening?stop():start();}}><Icon name="mic" size={18}/>{listening&&<span className="live-wave" aria-hidden="true">{levels.map((n,i)=><i key={i} style={{height:3+n*23}}/>)}</span>}</motion.button>
  {onMedia&&<><input hidden style={{display:'none'}} aria-label="上传记录图片" ref={file} type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={attach}/><button className="voice-image" type="button" disabled={listening||saved} aria-label="添加记录图片" onClick={()=>file.current.click()}><Icon name="image" size={18}/></button></>}
  {onSubmit&&<motion.button className={'voice-submit'+(saved?' is-saved':'')} type="button" aria-label={saved?'记录已保存':'确认旅行记录'} disabled={listening||finalizing||speechFinalizing||saved} onClick={submit} animate={{rotate:saved?360:0,scale:saved?1.18:1}} transition={reduced?{duration:0}:{type:'spring',stiffness:340,damping:20}}><Icon name={saved?'check':'return'} size={18}/></motion.button>}
 </div>;
 return <div className="journal-voice journal-voice-composer" data-rich={rich?'true':'false'}>
  <div className="journal-voice-frame" ref={frame} onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget)){cancelLongPress();dismissTools();}}}>
   <FloatingField as="textarea" ref={input} aria-label={label} rows={rows} value={value} onChange={e=>{dismissTools();onChange(e.target.value);}} placeholder={placeholder} readOnly={listening||saved}
    onSelect={()=>captureSelection()} onKeyDown={editorKeyDown} onKeyUp={selectionSoon}
    onPointerDown={beginSelectionPress} onPointerMove={e=>moveSelectionPress(e.clientX,e.clientY)} onPointerUp={()=>{cancelLongPress();selectionSoon();}} onPointerCancel={()=>{cancelLongPress();dismissTools();}}
    onTouchMove={e=>{const touch=e.touches[0];if(touch)moveSelectionPress(touch.clientX,touch.clientY);}} onTouchCancel={()=>{cancelLongPress();dismissTools();}}
    onContextMenu={e=>{if(!rich||readOnlyRef.current)return;e.preventDefault();cancelLongPress();selectAtCaret();captureSelection(true,'longpress');}}/>
   {fieldHost&&createPortal(actions,fieldHost)}
   {rich&&toolsOpen&&<Glass className="rich-format-tools voice-context-tools" role="toolbar" aria-label="文字格式" aria-orientation="horizontal" data-trigger={toolRange.trigger} data-selection-start={toolRange.start} data-selection-end={toolRange.end} data-placement={toolPosition.placement}
    initial={reduced?false:{opacity:0,scale:.94,y:4}} animate={{opacity:1,scale:1,y:0}} transition={reduced?{duration:0}:spring} style={{left:toolPosition.left,top:toolPosition.top}}
    onPointerDown={e=>{if(e.button===0)e.preventDefault();}}>
    <div className="voice-format-row" ref={tools}>{FORMATS.map(([id,name,icon],index)=><button key={id} ref={el=>toolButtons.current[index]=el} type="button" aria-label={name} tabIndex={toolIndex===index?0:-1} data-format={id} disabled={listening||saved}
     onFocus={()=>setToolIndex(index)} onKeyDown={e=>toolbarKeyDown(e,index)} onClick={()=>format(id)}>{icon}</button>)}</div>
   </Glass>}
  </div>
  {(status||interim||finalizing||speechFinalizing)&&<p className="voice-status" role="status" aria-live="polite">{finalizing||speechFinalizing?'正在收好录音与文字…':interim?'正在转写：'+interim:status}</p>}
 </div>;
}
