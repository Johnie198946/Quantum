import React,{forwardRef,useCallback,useLayoutEffect,useRef,useState} from 'react';

// Keep the native control, form value, validation and caller's DOM ref intact.
const FloatingField=forwardRef(function FloatingField({as:Control='input',value,defaultValue,onInput,onChange,onFocus,onBlur,placeholder,...props},forwardedRef){
 const input=useRef(null),[focused,setFocused]=useState(false),[uncontrolled,setUncontrolled]=useState(String(defaultValue??''));
 const ref=useCallback(el=>{input.current=el;if(typeof forwardedRef==='function')forwardedRef(el);else if(forwardedRef)forwardedRef.current=el;},[forwardedRef]);
 const filled=String(value!==undefined?value:uncontrolled).length>0;
 const label=props['aria-label']||placeholder||props.name||'填写内容';
 useLayoutEffect(()=>{
  const el=input.current;if(!el)return;setFocused(document.activeElement===el);
  // Trusted reset events can run microtasks before the browser restores defaults.
  let timer;const form=el.form,reset=()=>{clearTimeout(timer);timer=setTimeout(()=>{if(el.isConnected)setUncontrolled(el.value);},0);};
  form?.addEventListener('reset',reset);return()=>{clearTimeout(timer);form?.removeEventListener('reset',reset);};
 },[]);
 return <span className={'floating-field'+(Control==='textarea'?' floating-multiline':'')+(focused?' is-focused':'')+(filled?' is-filled':'')+(props.disabled?' is-disabled':'')}>
  <Control {...props} ref={ref} value={value} defaultValue={defaultValue} placeholder={placeholder} onInput={e=>{setUncontrolled(e.currentTarget.value);onInput?.(e);}} onChange={e=>{setUncontrolled(e.currentTarget.value);onChange?.(e);}} onFocus={e=>{setFocused(true);onFocus?.(e);}} onBlur={e=>{setFocused(false);setUncontrolled(e.currentTarget.value);onBlur?.(e);}}/>
  <span className="floating-title" aria-hidden="true">{label}</span>
 </span>;
});
export default FloatingField;
