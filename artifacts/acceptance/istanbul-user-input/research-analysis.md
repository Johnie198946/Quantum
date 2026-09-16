---
title: 伊斯坦布尔用户原文驱动编排：证据复核
date: 2026-09-16
tags:
  - research
  - presentation
  - istanbul
status: admitted
---

# 伊斯坦布尔用户原文驱动编排：证据复核

## 事实

### 可追溯输入与产品实测

用户原文保存在 `tests/fixtures/presentation/istanbul-source.md`。原始字节 SHA-256 为 `fc210e90867e714d1264ca75409cc31451d30c3025aa5b53f235cce7bd27359d`；按 UTF-8 读取并去除结尾换行后的规范文本 SHA-256 为 `7f817d92d614362b12b928d8547f90018397793acb0c8484ba11610111ca3440`。两种散列分别记录，不能混用。

Build 40 模拟器产品链实测使用 iPhone 17 Pro / iOS 26.1：XCTest `1 passed / 0 failed / 0 skipped`，`xcodebuild exit 0`；对应 iOS 单测为 `209 passed / 0 failed / 0 skipped`。最终工作流状态 `completed / 100%`，经过 outline、design、final 三道审批，生成 16 页 PPTX 和 16 页 PDF。来源追踪共 62 条、62 个唯一记录，16/16 页均有来源绑定，approval state 仅包含 `approved`。这些数字只证明本次受控样本的链路、来源绑定和下载验收，不证明旅游信息永久有效。

### 结论改变型事实及证据边界

1. **签证。** 土耳其驻北京大使馆 2024-09-26 公告说明：中国大陆普通护照持有人可申请旅游或商务用途、停留 30 天的单次入境电子签证。因此用户原文“中国大陆免签”不能原样进入攻略；Passport Control 是抵达后的入境审查，不能替代出发前签证。官方申请与资格应在出发前按 https://www.evisa.gov.tr/en/info/ 复核；中国护照范围的一手依据为 https://beijing-emb.mfa.gov.tr/Mission/ShowAnnouncement/411690 。未知项是个案资格、当期费用和附加条件。
2. **机场轨道交通。** Istanbul Airport 页面与 Metro İstanbul 线路图共同支持 M11 从 IST 到 Gayrettepe、在 Gayrettepe 换乘 M2，再从 Vezneciler 步行至 Laleli 换乘 T1 前往 Sultanahmet。Gayrettepe 不是 IST 后的“下一站”，只能表述为第一段轨道行程的终点。线路图不能证明机器颜色、165 里拉制卡费、ATM 手续费或实际步行负担。
3. **欧亚侧。** Üsküdar 市政府 Kuzguncuk 地图、OpenStreetMap 与 Britannica 的洲际地理说明相互独立支持：İstiklal、Galata、Ortaköy 和大巴扎在欧洲侧，Kuzguncuk 在亚洲侧。独立反例来源为 https://www.britannica.com/place/Istanbul ，底图许可边界见 https://www.openstreetmap.org/copyright 。因此整个 D2 不能统一标成“亚洲区”。
4. **轮渡时刻。** Şehir Hatları 是班次的一手来源，但正文核验受 Cloudflare 阻断；无法据此证明某日末班时间。成品只能要求出行前一天和当天复核 https://www.sehirhatlari.istanbul/en/timetables ，不能写死时刻。
5. **价格与商业条件。** 165 里拉、4500 里拉、“立省30欧”、ATM 手续费、Seven Hills 对非住客开放、餐厅营业时间及消费门槛均缺少同一时期且可读的一手支持，只能标为“作者当次经历/待核实”，不能升级为当前事实。

用户原文直接支持的内容包括 D1、D2 点位，Seven Hills、Sirkeci Lokantası 1912、Nusr-Et、Galata Konak Cafe 等具名节点，以及偏好地图、避坑、拍照、住宿和美食的编排目标。原文没有提供其他酒店榜单，因此不得新增酒店排名或价格背书。

## 分析

证据改变了三处核心编排。第一，签证页必须用一手来源纠正“免签”，并把个案条件留为未知。第二，机场进城不能被压缩成一次简单接驳，而应明确 M11→Gayrettepe→M2→Vezneciler/Laleli 步行→T1 的多段换乘。第三，D2 应改写为“欧洲新城→Bosphorus→亚洲岸”：İstiklal/Galata→Ortaköy→跨海至 Üsküdar→Kuzguncuk。

D1 的少折返顺序可派生为 Sultanahmet/Seven Hills 基地→蓝色清真寺/圣索菲亚→Sarayburnu→Çemberlitaş→大巴扎→苏莱曼尼→加拉塔大桥→巴拉特→返回码头看日落，但必须标记为基于坐标的编排建议，而不是用户原始编号。住宿只支持 Sultanahmet 区域级优先和 Seven Hills 的原文体验线索；美食只使用原文具名节点，不补造店名。

最强反例有三项：原文签证说法可能导致无法登机或入境；把 D2 全标为亚洲侧会造成地理错误；“公共交通不适合女生”是未经支持的泛化。最后一项应转换为可验证条件：行李数量、换乘次数、楼梯、步行、行动能力、老人儿童和到达时段。该转换保留可执行风险，不强化性别判断。

证据独立性边界也需明确：Istanbul Airport 与 Metro İstanbul 都属于官方交通来源，能相互补充但不是完全独立的第三方验证；Üsküdar 市政府、OSM 与 Britannica 分属市政、开放地理数据和独立百科，可作为地理结论的不同证据家族；用户经历性价格没有独立复核，所以不进入稳定事实层。

## 启示

产品链应把“原文真源”“外部事实”和“编排推断”分层。`text_material` 保存逐字原文和双 SHA-256；`external-supplement` 保存来源 URL、访问日期、版本与适用范围；`derived-with-rationale` 保存路线重排及理由。每个输出 claim 绑定原文 span、哈希、owner、tenant、client session、generation、审批状态和 slide ID；未知来源、跨 session、哈希不符、冲突重复或页面覆盖不完整时必须 fail closed。

地图底图使用 OSM 时保留 ODbL attribution；路线、点位、编号和标签保持可编辑。时效性价格和轮渡班次必须在成品中显式标注复核时间，避免将本次研究冻结成永久事实。

### 检索、失败与停止记录

- 查询轮次：3 轮；读取范围覆盖签证、机场轨道、洲际分区、轮渡时刻及一个独立地理反例。
- 失败：Şehir Hatları 正文受 Cloudflare 阻断；官方线路图不支持机器颜色、价格或步行体验结论。
- 剩余未知：签证个案资格/费用、165 里拉、4500 里拉、30 欧、ATM 手续费、Seven Hills 非住客规则、餐厅实时营业与消费门槛。
- 停止原因：会改变路线和风险提示的签证、轨道换乘及欧亚侧结论已由可读证据界定；继续检索无法把经历性价格转化为稳定事实，且来源正文预算已用完。
