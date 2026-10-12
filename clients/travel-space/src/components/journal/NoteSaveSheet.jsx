import React, { useState } from 'react';
import { useTravel } from '../../TravelContext';
import { images } from '../../data';
import FloatingField from '../FloatingField';
import { Icon, Primary, Sheet } from '../UI';
import NoteCoverCarousel from './NoteCoverCarousel';
import './note-save.css';

const contents = [
  ['每日行程', '包含每日行程', 'calendar'],
  ['照片与摄影参考', '包含照片与摄影参考', 'image'],
  ['地点与实用附录', '包含地点与实用附录', 'pin']
];

export default function NoteSaveSheet({ onClose }) {
  const { noteTitle, setNoteTitle, saveNotebook, notebookConfig, days, profile } = useTravel();
  const [cover, setCover] = useState(notebookConfig.cover);
  const [flags, setFlags] = useState(notebookConfig.flags);
  const [saving,setSaving]=useState(false),[error,setError]=useState('');
  const save = async () => {if(!noteTitle.trim()||saving)return;setSaving(true);setError('');try{await saveNotebook({cover,flags});}catch(e){setError(e.message);}finally{setSaving(false);}};

  return <Sheet label="生成旅行笔记" onClose={onClose} className="note-save note-save-compact">
    <header className="note-save-heading"><p className="eyebrow">MAKE IT YOURS</p><h2>收好这一程。</h2></header>
    <div className="note-save-body">
      <div className="note-save-composition">
        <figure className="note-save-cover glass">
          <img src={images[cover] || images.sakurajima} alt="选择的目的地封面"/>
          <figcaption><small>TRAVEL JOURNAL</small><strong>{noteTitle || '旅行手记'}</strong></figcaption>
          <span aria-hidden="true">山与海之间</span>
        </figure>
        <div className="note-save-title-column">
          <FloatingField aria-label="手记标题" value={noteTitle} onChange={event => setNoteTitle(event.target.value)}/>
          <div className="note-save-trip glass"><Icon name="leaf" size={16}/><strong>{profile.destination}</strong><span>{days.length} 天的安排<br/>山与海之间，慢慢走。</span></div>
        </div>
      </div>
      <NoteCoverCarousel value={cover} onChange={setCover}/>
      <section className="note-save-contents" aria-label="收进手记的内容">
        <header><h3>收进手记的内容</h3><span>{flags.filter(Boolean).length} / 3</span></header>
        <div className="note-save-content-grid">{contents.map(([title, label, icon], index) => <label className={'toggle-row glass note-save-option note-save-option-'+index} key={label}>
          <span><Icon name={icon} size={14}/><span>{title}</span></span>
          <input type="checkbox" aria-label={label} checked={flags[index]} onChange={event => setFlags(previous => previous.map((value, i) => i === index ? event.target.checked : value))}/>
        </label>)}</div>
      </section>
    </div>
    {error&&<p role="alert" className="lifecycle-error">{error}</p>}<footer className="note-save-actions"><span>{saving?'正在保存这本手记…':'沿途随时添一笔。'}</span><Primary disabled={!noteTitle.trim()||saving} onClick={save}>生成我的旅行手记</Primary></footer>
  </Sheet>;
}
