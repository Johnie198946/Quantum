export const trailNotes={};
export function notesForDay(day){const notes=day.travelNotes||{};return {categories:day.categories||[],transport:notes.transport||'路程与班次待核对。',food:notes.food||'三餐安排待补充。',stay:notes.stay||'住宿安排待补充。',play:notes.play||'参与条件与开放信息待核对。'};}
