import { destinations } from './components/mapRoute';
import sakurajima from './assets/sakurajima.png';
import senganen from './assets/senganen.png';
import ibusuki from './assets/ibusuki.png';
import kirishima from './assets/kirishima.png';
import map from './assets/map.png';
import neutral from './assets/magazine1000/scenery-0031.jpg';
export const images = { sakurajima, senganen, ibusuki, kirishima, map, neutral };
export let places = [];
export function replacePlaces(value){ places=value; }
export const initialDays = [];
export const defaultProfile = {destination:'',dates:'日期未定',party:'同行未定',count:'人数未定',budget:'未定',amount:'',currency:'人民币',pace:'未定',interests:[],additional:'',original:''};
export const interestOptions = ['寺社文化', '自然风光', '在地美食', '拍照打卡', '购物', '温泉', '亲子体验'];
export const stages = [
  { id: 'workflow', title: '工作流入口', hint: '右上角 + → 悬浮对话' },
  { id: 'chat', title: '悬浮对话', hint: '打字机 → 气泡 → 思考光球' },
  { id: 'discover', title: '景点与文件夹', hint: '滑走换一组 · 拖进文件夹' },
  { id: 'preferences', title: '完善计划', hint: '双指捏合 · 大图 / 三列 / 文字行' },
  { id: 'route', title: '旅行计划', hint: '真实坐标地图 · 每日行程' },
  { id: 'services', title: '交通与预订', hint: '往返 · 交通 · 住宿 · 三餐 · 体验' },
  { id: 'generating', title: '行程制作', hint: 'ThinkingOrb · 按住退回修改' },
  { id: 'adopt', title: '采用成稿', hint: '展开详情 · 排序与完成状态' },
  { id: 'guide', title: '攻略与保存', hint: '单列阅读 · 照片抽屉' },
  { id: 'notebook', title: '旅行手记', hint: '封面 · 日记 · 实用附录' },
  { id: 'trip', title: '这趟旅行', hint: '游前准备 · 今日安排 · 游后回顾' }
];
