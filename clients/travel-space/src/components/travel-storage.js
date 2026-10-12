import {normalizeJournalMedia} from './journal/journal-media';
import {initialDays,defaultProfile,images} from '../data';
export const DRAFT_KEY='quantum-travel-v4-draft-v1',SAVED_KEY='quantum-travel-v4-saved-v1';
export const defaultNotebookConfig={cover:'sakurajima',flags:[true,true,true]};
const knownCovers=['neutral','sakurajima','senganen','ibusuki','kirishima'];
export function readTravel(key){
 try{
  const value=JSON.parse(localStorage.getItem(key)||'null');
  if(!value||value.version!==1||!Array.isArray(value.days)||!value.days.length||value.days.length>90||new Set(value.days.map(d=>String(d.id))).size!==value.days.length||value.days.some(d=>!d||!['string','number'].includes(typeof d.id)||!Array.isArray(d.items)||d.items.length>100))return null;
  if(typeof value.profile?.destination!=='string'||!Array.isArray(value.profile.interests)||typeof value.noteTitle!=='string')return null;
  return {...value,profile:normalizeJournalMedia({...defaultProfile,...value.profile,todos:(Array.isArray(value.profile.todos)?value.profile.todos:[]).slice(0,200).filter(t=>t&&typeof t.id==='string'&&typeof t.title==='string').map(t=>({...t,source:typeof t.source==='string'?t.source.slice(0,240):'',title:t.title.slice(0,100),done:!!t.done}))}),days:value.days.map(d=>{const base=initialDays.find(x=>x.id===d.id);const validGeo=d.geo&&Number.isFinite(d.geo.lat)&&Number.isFinite(d.geo.lon)&&Math.abs(d.geo.lat)<=90&&Math.abs(d.geo.lon)<=180;return {...base,...d,image:base?.image||images.senganen,geo:validGeo?d.geo:Object.prototype.hasOwnProperty.call(d,'geo')?null:base?.geo};}),entries:value.entries&&typeof value.entries==='object'?value.entries:{},selected:Array.isArray(value.selected)?value.selected:[],extraCards:Array.isArray(value.extraCards)?value.extraCards:[],followUps:Array.isArray(value.followUps)?value.followUps:[],notebookConfig:knownCovers.includes(value.notebookConfig?.cover)&&value.notebookConfig.flags?.length===3?value.notebookConfig:defaultNotebookConfig};
 }catch{return null;}
}
export function serializableTravel(value){
 const {travelDocument,...profile}=value.profile;
 return {version:1,...value,profile,days:value.days.map(({image,...day})=>day),extraCards:value.extraCards.map(({image,...card})=>({...card,imageId:card.imageId||Object.keys(images).find(key=>images[key]===image)||'senganen'}))};
}
export function writeTravel(key,value){try{localStorage.setItem(key,JSON.stringify(serializableTravel(value)));return true;}catch{return false;}}
