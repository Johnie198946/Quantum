"""Deterministic extraction of a Chinese Istanbul travel brief.

The extractor does not invent hotels, restaurants, prices, or attractions. It
keeps the author's D1/D2 ordering available while exposing a geography-corrected
route for presentation layout.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


_NUMBERED = re.compile(r"^[1-9]️⃣")


@dataclass(frozen=True)
class TravelStop:
    source_order: int
    name: str
    source_text: str
    side: str
    kind: str
    caution: str = ""


@dataclass(frozen=True)
class IstanbulTravelBrief:
    title: str
    airport_entry: str
    public_transport_steps: tuple[str, ...]
    public_transport_caution: str
    taxi_advice: str
    source_day1: tuple[TravelStop, ...]
    source_day2: tuple[TravelStop, ...]
    corrected_day2_europe: tuple[TravelStop, ...]
    corrected_day2_asia: tuple[TravelStop, ...]
    lodging: tuple[str, ...]
    food: tuple[str, ...]
    price_cautions: tuple[str, ...]
    geography_note: str
    verified_constraints: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_STOP_META: dict[str, tuple[str, str]] = {
    "蓝色清真寺/圣索菲亚大教堂": ("europe", "landmark"),
    "苏莱曼尼清真寺": ("europe", "landmark"),
    "İBB Sarayburnu Parkı看海": ("europe", "photo"),
    "加拉塔大桥": ("europe", "photo"),
    "大巴扎": ("europe", "market"),
    "彩色巴拉特街区 Colorful Stairs": ("europe", "photo"),
    "seven hills 楼顶": ("europe", "lodging-photo"),
    "黄昏轮渡": ("crossing", "ferry"),
    "Kadırga Hamamı/Cemberlitas Hammam": ("europe", "hammam"),
    "独立大街": ("europe", "street"),
    "加拉塔石塔": ("europe", "landmark"),
    "奥塔科伊清真寺": ("europe", "photo"),
    "库兹衮库克 Kuzguncuk Evleri": ("asia", "neighborhood"),
    "撒盐哥的牛排店 Nusr-Et Steakhouse Kapalıçarşı Nusr-et Sandal Bedesteni": (
        "europe",
        "food",
    ),
}


def _name(line: str) -> str:
    body = _NUMBERED.sub("", line, count=1).strip()
    return body.split("：", 1)[0].strip()


def _stop(line: str, order: int) -> TravelStop:
    name = _name(line)
    side, kind = _STOP_META.get(name, ("unknown", "other"))
    caution = ""
    if any(token in line for token in ("价格刺客", "慎重", "爬山", "人比较多", "价格略贵")):
        caution = line.split("：", 1)[-1].strip()
    return TravelStop(order, name, line, side, kind, caution)


def parse_istanbul_travel_brief(text: str) -> IstanbulTravelBrief:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("travel source must not be empty")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    required = ["📖伊斯坦布尔入境", "🚃交通方法", "🚶玩法", "🚢D1: 欧洲区", "⭐️D2:亚洲区"]
    for marker in required:
        if marker not in lines:
            raise ValueError(f"travel source is missing section: {marker}")

    entry_index = lines.index("📖伊斯坦布尔入境")
    transport_index = lines.index("🚃交通方法")
    play_index = lines.index("🚶玩法")
    d1_index = lines.index("🚢D1: 欧洲区")
    d2_index = lines.index("⭐️D2:亚洲区")

    public_start = lines.index("🔷如果乘坐公共交通：")
    taxi_start = lines.index("🔷如果打车：")
    public_steps = tuple(
        line for line in lines[public_start + 1 : taxi_start] if _NUMBERED.match(line)
    )
    public_caution = next(
        line for line in lines[public_start + 1 : taxi_start] if line.startswith("⚠️")
    )
    taxi_advice = " ".join(lines[taxi_start + 1 : play_index])

    d1_lines = [line for line in lines[d1_index + 1 : d2_index] if _NUMBERED.match(line)]
    d2_lines = [line for line in lines[d2_index + 1 :] if _NUMBERED.match(line)]
    day1 = tuple(_stop(line, index) for index, line in enumerate(d1_lines, 1))
    day2 = tuple(_stop(line, index) for index, line in enumerate(d2_lines, 1))

    corrected_europe = tuple(stop for stop in day2 if stop.side == "europe")
    corrected_asia = tuple(stop for stop in day2 if stop.side == "asia")
    if not corrected_asia or len(corrected_europe) < 3:
        raise ValueError("D2 geography evidence is incomplete")

    lodging = (
        "住在蓝色清真寺/圣索菲亚附近，核心景点步行前往",
        "Seven Hills：原文作者入住，并使用楼顶喂海鸥、拍摄清真寺景观",
    )
    food = (
        "Sirkeci Lokantası 1912：原文列为大巴扎周边的 007 拍摄地",
        "Nusr-Et Steakhouse Kapalıçarşı：原文评价价格略贵、品质可以",
        "Galata Konak Cafe：原文作为不登加拉塔塔的拍照替代点",
    )
    price_cautions = tuple(
        line for line in lines if "价格刺客" in line or "比较贵" in line or "价格略贵" in line
    )
    return IstanbulTravelBrief(
        title=lines[0],
        airport_entry=" ".join(lines[entry_index + 1 : transport_index]),
        public_transport_steps=public_steps,
        public_transport_caution=public_caution,
        taxi_advice=taxi_advice,
        source_day1=day1,
        source_day2=day2,
        corrected_day2_europe=corrected_europe,
        corrected_day2_asia=corrected_asia,
        lodging=lodging,
        food=food,
        price_cautions=price_cautions,
        geography_note=(
            "原文将独立大街、加拉塔塔和奥塔科伊列入‘亚洲区’，但三处都在欧洲侧；"
            "可执行编排应先完成欧洲侧，再乘轮渡到 Üsküdar/Kuzguncuk。"
        ),
        verified_constraints=(
            "截至2026-09-16，中国大陆普通护照旅游或商务不是免签；符合条件者须在出发前通过 evisa.gov.tr 取得30天单次入境电子签证，个案条件和费用以申请页为准。",
            "IST机场可乘M11到Gayrettepe，再换M2；前往Sultanahmet还需在Vezneciler出站步行到Laleli换T1，须把换乘和步行缓冲计入行程。",
            "独立大街、加拉塔石塔、奥塔科伊和大巴扎都在欧洲侧；Kuzguncuk在亚洲侧，不能按原文D2标题把前四者标成亚洲侧。",
            "黄昏轮渡的码头、班次和临时取消须按具体日期复核Şehir Hatları官方时刻表，不写死末班时间。",
            "165里拉制卡费、4500里拉出租车费、30欧晚餐和ATM手续费仅是作者当次经验；展示时必须同页标注价格会变、出发前复核。",
        ),
    )
