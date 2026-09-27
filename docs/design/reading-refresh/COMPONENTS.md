# 阅读页组件与素材清单

视觉基准：`approved-reference.png`，用户于 2026-09-27 确认的四屏原型。
实现入口：MainTabView → KnowledgeView → SubscriptionCenterView。仅视觉层变化，不另建数据服务。

## 页面与组件

|区域|实现|布局/状态|数据及行为|
|---|---|---|---|
|页面底色/文字/边框|AppTheme.Reading|纸白FCFCFA、墨色182126、边框E3E5ED；14pt圆角|局部token，复用现有primary与语义色|
|页头与笔记/书架切换|KnowledgeView.libraryHeader|20pt边距、小身份标题、28pt级文本Tab、2pt选中线；装饰不接收事件|原showingBookshelf状态|
|笔记搜索|knowledgeSearchField|48pt高、细描边、清除按钮|原searchText与store.search|
|笔记范围|scopePicker|文字Tab与短下划线，44pt点击区域|原all/pinned/daily|
|标签与主题|ReadingChip|胶囊；选中薄荷底；44pt点击区|原标签集合/主题筛选|
|笔记卡片|ReadingNoteCard + ReadingNoteTile + noteSection|两列；14pt内距；白/杏/紫轮替；纸角/胶带；大字号单列|原标题、摘要、相对时间、标签、反链、置顶、打开|
|卡片操作|noteSection|右扫置顶；左扫弹出删除确认；长按及辅助功能等价入口|原store.togglePin和删除确认，不直接跳过确认|
|笔记操作栏|noteActions + safeAreaInset|48pt按钮；横向双按钮；大字号纵向|原createNote/openDailyNote|
|书架搜索/添加|bookshelfCollections + bookshelfSearch|搜索与44pt+按钮同排|搜索聚焦/搜索文本；原showsAllBooks|
|阅读范围/数量|bookshelfScopeTabs|文字＋真实数量＋下划线|沿用books(for:)统计|
|在读区|recentReadingSection/recentBookCard|横向轮播；封面96×160pt；卡片326pt；内容自适应高|真实标题、作者、进度、打开阅读器与查看全部|
|主题陈列|topicDiscoverySection/topicBookCard|横向封面陈列，标题在下；保留最多8项与原筛选|原filterBooks与inspectedBook|
|书单区|bookshelfListSection|已有书单横向展示；58pt新建入口|原编辑/新建逻辑|
|系统刊物|systemPublications|原生DisclosureGroup，默认关闭；展开动画遵守减弱动态效果|原最新期分组、订阅禁用/忙碌/错误处理|
|编辑页|bookListEditor/bookSelectionRow|独立标题/输入/书籍行；封面、阅读入口与Toggle分区|原保存验证、选择集合、阅读、取消、删除与草稿保留|
|底部导航|QuantumFloatingTabBar|阅读Tab改为64pt平面导航；其他Tab保留原外观|不变更路由、状态、工作流活动条|
|标题行|ReadingSectionHeading|18pt级标题与小插画|纯展示|
|装饰层|ReadingArtwork|按实际位置缩放；不接收点击，对VoiceOver隐藏|无业务状态|

## 每个交互图标

图标保持平台矢量 SF Symbols，不把截图图标切成模糊PNG。系统选中状态、禁用状态和无障碍标签由原生控件负责。

|功能|SF Symbol/原生控件|典型尺寸|
|---|---|---|
|更多|ellipsis|20pt，44pt点击区|
|搜索|magnifyingglass|16–18pt，书架聚焦按钮44pt|
|清空搜索|xmark.circle.fill|16pt，44pt点击区|
|新建笔记|square.and.pencil|正文尺寸，48pt按钮|
|今日日记|sun.max|正文尺寸，48pt按钮|
|添加书籍/书单|plus|20pt，至少44pt|
|进入/查看全部|chevron.right / 原文箭头|12pt，至少44pt|
|置顶|pin / pin.fill|12–16pt|
|删除|trash|原生菜单|
|反向链接|link|caption|
|阅读/书单|book / books.vertical|16pt/原生标签|
|选书|Toggle|系统开关，44pt高点击区|
|展开/收起刊物|chevron.down / chevron.up|DisclosureGroupStyle，原生按钮和展开状态|
|装饰叶子|leaf|12pt；非交互|
|卡片装饰书签|bookmark.fill|16pt；非交互|
|首页|house / house.fill|18pt|
|阅读|book / book.fill|18pt|
|工作流|square.stack.3d.up / square.stack.3d.up.fill|18pt|
|我的|person / person.fill|18pt|

## 独立透明插画

全部由内置imagegen基于批准图提取重绘，PNG保留alpha；原图仅作为视觉基准，运行时不加载整页截图。

|Asset Catalog名称|内容|位置|
|---|---|---|
|reading_notes|纸飞机＋打开的笔记本＋淡薄荷底|笔记页头|
|reading_reading|打开的书＋嫩芽|书架页头、书单编辑页头|
|reading_growth|双书叠放＋嫩芽|笔记奇数卡片留白、我的书单标题右侧|

生成提示词共同约束：从approved-reference中只提取指定装饰，透明背景，保留青绿/雾蓝/浅紫插画风格，无UI文字，无按钮，无水印，无额外元素。分别提取第一屏页头、第二屏页头、第一屏下方留白三处装饰。
纸角与胶带采用原生Shape/Rectangle绘制，不新增图片；真实书籍封面沿用PublicationBookCover的鉴权媒体加载与既有回退。

## 保真边界与验收

- 设计中的文字/书籍/进度是示意；线上仍用真实数据，不覆盖真实封面。
- 图片不是可执行尺寸规范，字体渲染与设备比例会产生差异；以相同设备真实截图逐项校准，不虚报像素一致率。
- 搜索、置顶/删除、范围/标签、切换、阅读返回、选书、未保存草稿、折叠刊物和保存验证必须可用。
- 在独立模拟器用DEBUG预览数据验证；预览夹具不写入生产账号，未执行真实订阅或书单保存请求。
- 大字号允许单列与自适应高度；交互图标至少44pt点击区；装饰不干扰辅助功能。
