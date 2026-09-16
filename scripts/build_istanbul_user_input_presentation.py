#!/usr/bin/env python3
"""Build an Istanbul deck from the user's exact Chinese travel post."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


from backend.services.presentation_map import resolve_istanbul_landmarks
from backend.services.presentation_renderer import build_pptx, render_pptx_pdf
from backend.services.presentation_source_trace import (
    bind_claims_to_slides,
    build_source_claims,
    build_trace_manifest,
    validate_trace_matrix,
)
from backend.services.presentation_travel_brief import parse_istanbul_travel_brief
from backend.services.presentation_visual_gates import run_visual_gates
from scripts.build_istanbul_presentation import (
    FIXED_TIME,
    _material,
    _svg_icon,
    _theme,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/presentation/istanbul-source.md"
EXTERNAL_SOURCES = [
    {
        "source_id": "tr-mfa-cn-evisa-2024-09-26",
        "claim": "中国普通护照当前应按土耳其官方 e-Visa/签证要求核验，不能把用户原文的‘免签’直接作为现行事实。",
        "url": "https://beijing-emb.mfa.gov.tr/Mission/ShowAnnouncement/411690",
        "kind": "official-primary",
        "checked_at": "2026-09-16",
        "slide_ids": ["slide-002"],
    },
    {
        "source_id": "metro-istanbul-network-map-v3-rev20-1",
        "claim": "官方轨道交通图支持 M11、Gayrettepe、M2、Vezneciler、Laleli 与 T1/Sultanahmet 的路线元素。",
        "url": "https://www.metro.istanbul/Content/assets/uploaded/%C4%B0stanbul%20Rayl%C4%B1%20Sistemler%20Haritas%C4%B1.pdf",
        "kind": "official-primary",
        "checked_at": "2026-09-16",
        "slide_ids": ["slide-002", "slide-003"],
    },
    {
        "source_id": "ist-airport-m11-public-transport",
        "claim": "Istanbul Airport 官方页面确认 M11 连接机场、Kağıthane 与 Gayrettepe；前往老城仍需后续换乘。",
        "url": "https://istairport.com/en/airport/airport-transportation/intercity-transportation/public-transportation?locale=ru",
        "kind": "official-primary",
        "checked_at": "2026-09-16",
        "slide_ids": ["slide-002", "slide-003"],
    },
    {
        "source_id": "osm-copyright",
        "claim": "地图底图必须注明 OpenStreetMap contributors，并遵守 ODbL。",
        "url": "https://www.openstreetmap.org/copyright",
        "kind": "official-primary",
        "checked_at": "2026-09-16",
        "slide_ids": ["slide-004", "slide-006"],
    },
    {
        "source_id": "uskudar-kuzguncuk-map-2020",
        "claim": "Üsküdar/Kuzguncuk 在亚洲侧，Beşiktaş/Ortaköy 在欧洲侧。",
        "url": "https://uskudar.bel.tr/userfiles/files/2019/Kuzguncuk%20Haritas%C4%B1.pdf",
        "kind": "official-primary",
        "checked_at": "2026-09-16",
        "slide_ids": ["slide-006", "slide-007"],
    },
    {
        "source_id": "sehir-hatlari-timetables",
        "claim": "具体轮渡班次必须按航线、日期与星期在出发前复核；本次自动提取被官方站点 Cloudflare 403 阻挡，因此不写死任何班次。",
        "url": "https://www.sehirhatlari.istanbul/en/timetables",
        "kind": "official-primary",
        "checked_at": "2026-09-16",
        "slide_ids": ["slide-005", "slide-007"],
        "verification_state": "current-schedule-unverified",
        "access_error": "HTTP 403 / Cloudflare browser verification",
    },
    {
        "source_id": "britannica-istanbul-geography-2026-06-03",
        "claim": "独立反例：博斯普鲁斯海峡分隔欧洲伊斯坦布尔与亚洲岸的 Üsküdar/Kadıköy；金角湾两侧仍都属于欧洲侧。",
        "url": "https://www.britannica.com/place/Istanbul",
        "kind": "independent-secondary",
        "checked_at": "2026-09-16",
        "slide_ids": ["slide-006", "slide-007"],
    },
]


def _load_photos(fixtures: Path, assets: Path) -> dict[str, dict]:
    catalog = {
        "cover": ("blue-mosque.jpg", "https://commons.wikimedia.org/wiki/File:Blue_Mosque_Courtyard_Dusk_Wikimedia_Commons.jpg", "Benh LIEU SONG", "CC-BY-SA-3.0", "https://creativecommons.org/licenses/by-sa/3.0/"),
        "bosphorus": ("karakoy-ferry.jpg", "https://commons.wikimedia.org/wiki/File:Karak%C3%B6y_Mars_2013_02.jpg", "Arild Vågen", "CC-BY-SA-3.0", "https://creativecommons.org/licenses/by-sa/3.0/"),
        "old-city": ("hagia-sophia.jpg", "https://commons.wikimedia.org/wiki/File:Hagia_Sophia_Mars_2013.jpg", "Arild Vågen", "CC-BY-SA-3.0", "https://creativecommons.org/licenses/by-sa/3.0/"),
        "cistern": ("basilica-cistern.jpg", "https://commons.wikimedia.org/wiki/File:Cisterna_Bas%C3%ADlica,_Estambul,_Turqu%C3%ADa,_2024-09-28,_DD_58-60_HDR.jpg", "Diego Delso", "CC-BY-SA-4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
        "palace": ("topkapi.jpg", "https://commons.wikimedia.org/wiki/File:Topkapi_Palace_Bosphorus.JPG", "Gryffindor", "Public-Domain", "https://commons.wikimedia.org/wiki/Template:PD-self"),
    }
    photos = {}
    for name, (filename, source_url, author, license_id, license_url) in catalog.items():
        data = (fixtures / filename).read_bytes()
        path = assets / filename
        path.write_bytes(data)
        photos[name] = _material(
            data,
            name=path.name,
            mime="image/jpeg",
            source_url=source_url,
            author=author,
            license_id=license_id,
            license_url=license_url,
        )
    return photos



def _points(names: list[str]) -> list[dict]:
    return [
        {
            "name": point.name,
            "longitude": point.longitude,
            "latitude": point.latitude,
            "side": point.side,
            "detail": point.detail,
        }
        for point in resolve_istanbul_landmarks(names)
    ]


_SLIDE_CLAIM_INDEXES = {
    1: (1, 2, 3, 4),
    2: (6, 7, 8, 11, 12, 13),
    3: tuple(range(10, 20)),
    4: (22, 23, 27, 28, 29, 30, 31, 32, 33, 34, 35),
    5: tuple(range(23, 36)),
    6: tuple(range(36, 43)),
    7: tuple(range(37, 43)),
    8: (23, 32),
    9: (30, 39, 42),
    10: (14, 15, 16, 18, 19, 24, 27, 29, 31, 33, 35, 38, 39, 40, 41, 42),
    11: (2, 28, 29, 32, 33, 39, 40, 41),
    12: (5, 9, 17, 20, 21, 22, 36),
}


def build_package(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    # The Markdown file ends with a storage newline; the chat payload does not.
    source_text = SOURCE.read_text(encoding="utf-8").rstrip("\r\n")
    brief = parse_istanbul_travel_brief(source_text)

    assets = output / "assets"
    assets.mkdir(exist_ok=True)
    photos = _load_photos(ROOT / "tests/fixtures/presentation/assets", assets)
    icons = {}
    for name in ("landmark", "ferry", "food", "camera", "walk", "bridge"):
        data = _svg_icon(name)
        path = assets / f"icon-{name}.svg"
        path.write_bytes(data)
        icons[name] = _material(data, name=path.name, mime="image/svg+xml")

    map_data = (ROOT / "tests/fixtures/presentation/assets/istanbul-osm.png").read_bytes()
    map_path = assets / "istanbul-osm.png"
    map_path.write_bytes(map_data)
    map_material = _material(
        map_data,
        name=map_path.name,
        mime="image/png",
        source_url="https://www.openstreetmap.org/#map=13/41.025/28.990",
        author="© OpenStreetMap contributors",
        license_id="ODbL-1.0",
        license_url="https://www.openstreetmap.org/copyright",
    )
    d1_bounds = (28.94, 40.995, 29.01, 41.04)
    d1_map_data = (
        ROOT / "tests/fixtures/presentation/assets/istanbul-osm-d1.png"
    ).read_bytes()
    d1_map_path = assets / "istanbul-osm-d1.png"
    d1_map_path.write_bytes(d1_map_data)
    d1_map_material = _material(
        d1_map_data,
        name=d1_map_path.name,
        mime="image/png",
        source_url="https://www.openstreetmap.org/#map=14/41.018/28.975",
        author="© OpenStreetMap contributors",
        license_id="ODbL-1.0",
        license_url="https://www.openstreetmap.org/copyright",
    )

    slides = [
        {
            "layout": "hero_photo",
            "title": "穷游伊斯坦布尔 · 躲开价格刺客",
            "subtitle": "两天地图攻略｜住哪里｜吃什么｜在哪里拍大片",
            "photo": photos["cover"],
            "caption": "蓝色清真寺 · Benh LIEU SONG · CC BY-SA 3.0",
        },
        {
            "layout": "timeline",
            "title": "落地先做对 4 件事",
            "subtitle": "原文经验保留；签证与价格单独标记时效风险",
            "events": [
                {"label": "入境", "title": "先办电子签", "detail": "中国普通护照并非免签；出发前查 evisa.gov.tr，抵达后仍需到 Passport Control 接受入境审查"},
                {"label": "现金", "title": "9号门附近 ATM", "detail": "原文建议找蓝色 İş Bankası，并称汇率较好、免本地手续费"},
                {"label": "交通卡", "title": "负二楼购卡", "detail": "原文：顺 METRO 标志，蓝色机器制卡费 165 里拉；价格需当日复核"},
                {"label": "路线", "title": "M11 → M2 → T1", "detail": "可用原文所述 Yandex Metro 查路；Gayrettepe 换 M2，Vezneciler 出站步行至 Laleli 换 T1"},
            ],
        },
        {
            "layout": "data_story",
            "title": "机场到老城：便宜与省力二选一",
            "subtitle": "价格按原文呈现，不作为实时承诺",
            "metric": "3",
            "unit": "段轨交",
            "body": "公共交通适合行李少、脚力好的人；携大件行李、老人儿童或行动不便者，应优先减少换乘。不要把性别作为出行能力判断标准。",
            "facts": [
                "公共交通：M11 → M2 → 步行 → T1；Gayrettepe 不是 IST 后的下一站",
                "原文称 Uber 到蓝色清真寺约 4500 里拉；下单前看实时价",
                "Uber 的价值是路线记录与应用内支付，不保证比出租车便宜",
                "ATM 位置、手续费、交通卡价格及运营时间均须抵达前复核",
            ],
        },
        {
            "layout": "geo_route_map",
            "title": "D1 欧洲区 · 原文 9 站地图",
            "subtitle": "在不删原文点位的前提下重排：老城步行 → 金角湾/巴拉特 → 日落轮渡",
            "map": d1_map_material,
            "attribution": "© OpenStreetMap contributors · ODbL 1.0",
            "bounds": list(d1_bounds),
            "points": _points([
                "Seven Hills", "Blue Mosque / Hagia Sophia", "Sarayburnu Park", "Cemberlitas Hammam",
                "Grand Bazaar", "Suleymaniye Mosque", "Galata Bridge", "Balat Colorful Stairs",
                "Eminonu Ferry",
            ]),
        },
        {
            "layout": "timeline",
            "title": "D1 怎么玩：景点、脚力和拍摄窗口",
            "subtitle": "按原文重排为可执行顺序",
            "events": [
                {"label": "清晨", "title": "蓝色清真寺 / 圣索菲亚", "detail": "住附近步行；圣索菲亚仅建议历史爱好者付费进入"},
                {"label": "上午", "title": "苏莱曼尼清真寺", "detail": "山头步行，怕爬坡者可跳过"},
                {"label": "午前", "title": "Sarayburnu Parkı", "detail": "从居尔哈尼公园穿到海边，人少看海"},
                {"label": "中午", "title": "加拉塔大桥", "detail": "看当地人钓鱼，也是原文重点出片位"},
                {"label": "下午", "title": "大巴扎 / 巴拉特", "detail": "大巴扎快逛；巴拉特喝茶发呆，但要爬坡"},
                {"label": "傍晚", "title": "Seven Hills / 黄昏轮渡", "detail": "楼顶喂海鸥；轮渡须按日期、码头和官方时刻表复核，不写死班次"},
                {"label": "夜间", "title": "土耳其浴二选一", "detail": "Kadırga 更省；Çemberlitaş 知名度高、原文判断更贵"},
            ],
        },
        {
            "layout": "geo_route_map",
            "title": "D2 纠偏地图 · 欧洲侧拍照 → 亚洲侧发呆",
            "subtitle": "独立大街、加拉塔塔、奥塔科伊在欧洲侧；过海后才到 Üsküdar / Kuzguncuk",
            "map": map_material,
            "attribution": "© OpenStreetMap contributors · ODbL 1.0",
            "points": _points(["Istiklal Street", "Galata Tower", "Ortakoy Mosque", "Uskudar", "Kuzguncuk"]),
        },
        {
            "layout": "timeline",
            "title": "D2 可执行玩法",
            "subtitle": "修正‘亚洲区’标题下的地理混排，不删原有玩法",
            "events": [
                {"label": "上午", "title": "独立大街 → 加拉塔塔", "detail": "都在欧洲侧；拍照可用 Galata Konak Cafe 替代登塔"},
                {"label": "午后", "title": "奥塔科伊清真寺", "detail": "仍在欧洲侧；日落与黄昏轮渡二选一"},
                {"label": "过海", "title": "轮渡到 Üsküdar", "detail": "把跨洲动作在地图中明确标出，避免折返"},
                {"label": "下午", "title": "Kuzguncuk", "detail": "亚洲区休闲街区，买咖啡、慢走发呆"},
                {"label": "餐饮", "title": "Nusr-Et 移回 D1/老城", "detail": "该店位于大巴扎，不应作为亚洲区路线终点"},
            ],
        },
        {
            "layout": "data_story",
            "title": "住哪里：原文只支持 1 个区域 + 1 个具名选择",
            "subtitle": "不擅自扩写酒店榜单",
            "metric": "1",
            "unit": "个步行基地",
            "body": "首选 Sultanahmet（蓝色清真寺 / 圣索菲亚附近）：D1 核心景点可步行，减少拖行李和多次换乘。",
            "facts": [
                "Seven Hills：原文作者入住，楼顶可喂海鸥、拍清真寺景观",
                "选择时检查坡度、是否有电梯、拖箱距离",
                "原文没有更多酒店实测，输出不虚构第二家酒店",
            ],
        },
        {
            "layout": "icon_facts",
            "title": "吃什么 / 去哪拍：只用原文出现的 3 个点",
            "subtitle": "餐厅与拍照替代位分开；价格、营业状态均须出发前复核",
            "items": [
                {"icon": icons["food"], "title": "Sirkeci Lokantası 1912", "detail": "大巴扎周边；原文称 007 拍摄地，适合顺路"},
                {"icon": icons["landmark"], "title": "Nusr-Et Kapalıçarşı", "detail": "位于大巴扎；原文评价价格略贵、品质可以"},
                {"icon": icons["camera"], "title": "Galata Konak Cafe", "detail": "仅作不登加拉塔塔的拍照替代点；原文称可省 30 欧，非餐食品质推荐"},
                {"icon": icons["bridge"], "title": "绑定地图", "detail": "两家餐厅跟大巴扎/老城走，不另起一条觅食路线"},
                {"icon": icons["walk"], "title": "住宿减步行", "detail": "住 Sultanahmet，把体力留给苏莱曼尼、巴拉特和加拉塔坡路"},
                {"icon": icons["ferry"], "title": "跨海不折返", "detail": "去 Kuzguncuk 当天不要再回大巴扎吃 Nusr-Et"},
            ],
        },
        {
            "layout": "timeline",
            "title": "真正有用的“避坑 × 出片”清单",
            "subtitle": "把原文态度转成决策，而不是改写成城市百科",
            "events": [
                {"label": "脚力", "title": "三段坡路", "detail": "苏莱曼尼、巴拉特、加拉塔涉及坡路；行李多或行动不便就减站"},
                {"label": "出片", "title": "三个窗口", "detail": "加拉塔大桥钓鱼、Seven Hills 海鸥、奥塔科伊/轮渡日落"},
                {"label": "门票", "title": "按兴趣付费", "detail": "圣索菲亚与加拉塔塔按兴趣决定，不为打卡强上"},
                {"label": "黄昏", "title": "日落只排一个", "detail": "黄昏轮渡与奥塔科伊日落冲突，两天内不要重复抢同一窗口"},
                {"label": "价格", "title": "原文价不当实时价", "detail": "4500 里拉、165 里拉、30 欧保留为原文经验，并标记实时复核"},
                {"label": "跨洲", "title": "避免折返", "detail": "先走完欧洲侧，再从 Üsküdar 衔接 Kuzguncuk"},
            ],
        },
        {
            "layout": "photo_collage",
            "title": "原文对应的四种画面",
            "subtitle": "清真寺、海峡、历史空间与皇宫海岸",
            "photos": [
                {"material": photos["old-city"], "caption": "圣索菲亚 · Arild Vågen"},
                {"material": photos["bosphorus"], "caption": "Karaköy 轮渡 · Arild Vågen"},
                {"material": photos["cistern"], "caption": "地下水宫 · Diego Delso"},
                {"material": photos["palace"], "caption": "托普卡帕宫海岸 · Gryffindor"},
            ],
        },
        {
            "layout": "quote_photo",
            "title": "两天编排的核心",
            "quote": "不是把景点堆满，而是用地图减少折返：住在老城、把坡路留给脚力、把黄昏留给轮渡或奥塔科伊。",
            "attribution": "基于用户原文的可执行编排",
            "photo": photos["bosphorus"],
        },
    ]
    spec = {
        "title": "穷游伊斯坦布尔 · 躲开价格刺客",
        "subtitle": "用户原文驱动的两天地图攻略",
        "theme": _theme(),
        "slides": slides,
    }
    spec_path = output / "istanbul-user-input-deck-spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    pptx_path = output / "istanbul-user-input.pptx"
    pptx_path.write_bytes(build_pptx(json.dumps(spec, ensure_ascii=False)))
    pdf_path = output / "istanbul-user-input.pdf"
    pdf_path.write_bytes(render_pptx_pdf(pptx_path))

    claims = build_source_claims(
        source_text,
        source_id="fixture.istanbul.user.v1",
        source_client_session_id="session-istanbul-user-input",
        approval_state="approved",
    )
    bindings = [
        {
            "claim_id": claims[claim_index - 1]["claim_id"],
            "slide_id": f"slide-{slide_index:03d}",
            "transform": "summarized",
        }
        for slide_index, claim_indexes in _SLIDE_CLAIM_INDEXES.items()
        for claim_index in claim_indexes
    ]
    records = bind_claims_to_slides(claims, bindings)
    validated = validate_trace_matrix(
        records,
        source_texts={"fixture.istanbul.user.v1": source_text},
        source_client_session_id="session-istanbul-user-input",
    )
    trace_path = output / "source-trace.json"
    trace_path.write_text(json.dumps(build_trace_manifest(validated), ensure_ascii=False, indent=2) + "\n")
    evidence_path = output / "external-source-manifest.json"
    external_sources = [
        {
            **source,
            "content_hash": hashlib.sha256(source["claim"].encode()).hexdigest(),
            "source_client_session_id": "session-istanbul-user-input",
            "verification_state": source.get("verification_state", "verified"),
            "recheck_required": True,
        }
        for source in EXTERNAL_SOURCES
    ]
    evidence_path.write_text(json.dumps({"sources": external_sources}, ensure_ascii=False, indent=2) + "\n")
    fact_check_path = output / "fact-check-matrix.json"
    fact_check_path.write_text(json.dumps({
        "schema_version": 1,
        "checked_at": "2026-09-16",
        "checks": [
            {
                "id": "visa-mainland-china",
                "source_statement": "土耳其对中国大陆免签",
                "verdict": "contradicted",
                "correction": "中国大陆普通护照旅游或商务不是免签；符合条件者须在出发前申请30天单次入境电子签证，个案条件和费用以 evisa.gov.tr 为准。",
                "source_ids": ["tr-mfa-cn-evisa-2024-09-26"],
                "effect_on_orchestration": "入境页在 Passport Control 之前增加电子签准备，不得沿用免签表述。",
            },
            {
                "id": "ist-m11-old-city",
                "source_statement": "M11第一站坐到Gayrettepe，再换M2、步行换T1到Sultanahmet",
                "verdict": "route-valid-wording-corrected",
                "correction": "M11可到Gayrettepe并换M2；Gayrettepe不是机场后的下一站，前往Sultanahmet还包含Vezneciler到Laleli的站外步行和T1换乘。",
                "source_ids": ["ist-airport-m11-public-transport", "metro-istanbul-network-map-v3-rev20-1"],
                "effect_on_orchestration": "路线页保留链路但写清两次换乘、站外步行和行李/体力缓冲。",
            },
            {
                "id": "day2-continent-grouping",
                "source_statement": "D2亚洲区包含独立大街、加拉塔石塔、奥塔科伊、Kuzguncuk和大巴扎餐厅",
                "verdict": "contradicted",
                "correction": "独立大街、加拉塔石塔、奥塔科伊和大巴扎均在欧洲侧；Kuzguncuk在亚洲侧。",
                "source_ids": ["uskudar-kuzguncuk-map-2020", "britannica-istanbul-geography-2026-06-03"],
                "effect_on_orchestration": "D2地图先完成欧洲侧，再过海到Üsküdar/Kuzguncuk；大巴扎餐厅归回D1老城。",
            },
            {
                "id": "ferry-timetable",
                "source_statement": "黄昏轮渡算好时间即可",
                "verdict": "unknown-until-travel-date",
                "correction": "必须先指定码头、航线、日期和星期；本次无法穿过官方站点Cloudflare验证取得具体班次。",
                "source_ids": ["sehir-hatlari-timetables"],
                "effect_on_orchestration": "不写死班次；在行程中设置出发前一天及当天复核门。",
            },
            {
                "id": "volatile-prices-and-fees",
                "source_statement": "ATM免本地手续费、制卡费165里拉、出租车4500里拉、立省30欧",
                "verdict": "author-experience-time-sensitive",
                "correction": "这些数值和手续费均只作为作者当次经验，不作为2026固定价格。",
                "source_ids": [],
                "effect_on_orchestration": "相关页面同页标注价格会变并要求出发前复核。",
            },
        ],
    }, ensure_ascii=False, indent=2) + "\n")

    def claim_ids(*terms: str) -> list[str]:
        return [
            claim["claim_id"]
            for claim in claims
            if any(term.casefold() in claim["claim"].casefold() for term in terms)
        ]

    coverage_matrix = {
        "schema_version": 1,
        "input_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
        "claim_count": len(claims),
        "bound_claim_count": len({record["claim_id"] for record in validated}),
        "trace_record_count": len(validated),
        "unbound_claim_count": len(claims) - len({record["claim_id"] for record in validated}),
        "requirements": [
            {"id": "entry", "status": "covered-with-conflict", "classification": "source-backed + external-correction", "slides": ["slide-002"], "claim_ids": claim_ids("免签", "Passport Control")},
            {"id": "airport-transport", "status": "covered", "classification": "source-backed", "slides": ["slide-002", "slide-003"], "claim_ids": claim_ids("ATM", "METRO", "M11", "公共交通", "打车", "uber")},
            {"id": "day1-map", "status": "covered", "classification": "derived-with-rationale", "slides": ["slide-004", "slide-005"], "claim_ids": claim_ids("蓝色清真寺", "苏莱曼尼", "Sarayburnu", "加拉塔大桥", "大巴扎", "巴拉特", "seven hills", "黄昏轮渡", "Hamam")},
            {"id": "day2-map", "status": "covered-with-geography-correction", "classification": "source-backed + derived-with-rationale", "slides": ["slide-006", "slide-007"], "claim_ids": claim_ids("独立大街", "加拉塔石塔", "奥塔科伊", "Kuzguncuk", "Nusr-Et")},
            {"id": "lodging", "status": "covered-limited", "classification": "source-backed", "slides": ["slide-008"], "claim_ids": claim_ids("住在附近", "我就住在这里"), "limit": "原文只支持 Sultanahmet 区域与 Seven Hills 一个具名选择。"},
            {"id": "food", "status": "covered-limited", "classification": "source-backed", "slides": ["slide-009"], "claim_ids": claim_ids("Lokantası", "Steakhouse", "Galata Konak Cafe"), "limit": "原文没有支持更广泛的餐厅榜单。"},
            {"id": "price-traps", "status": "covered-with-staleness-warning", "classification": "source-backed", "slides": ["slide-003", "slide-009", "slide-010"], "claim_ids": claim_ids("价格刺客", "165里拉", "4500里拉", "30欧", "比较贵", "价格略贵")},
            {"id": "photo-and-slow-play", "status": "covered", "classification": "source-backed", "slides": ["slide-005", "slide-007", "slide-010", "slide-011"], "claim_ids": claim_ids("拍照", "出片", "日落", "黄昏", "发呆", "喂海鸥")},
        ],
    }
    coverage_path = output / "content-coverage-matrix.json"
    coverage_path.write_text(json.dumps(coverage_matrix, ensure_ascii=False, indent=2) + "\n")

    map_report = {
        "schema_version": 1,
        "base": "OpenStreetMap raster under ODbL 1.0",
        "editable_overlays": True,
        "routes": [
            {"slide_id": "slide-004", "bounds": list(d1_bounds), "strategy": "reordered-without-dropping-user-points", "points": [point["name"] for point in slides[3]["points"]]},
            {"slide_id": "slide-006", "bounds": [28.85, 40.97, 29.13, 41.08], "strategy": "correct-Europe-to-Asia-crossing", "points": [point["name"] for point in slides[5]["points"]]},
        ],
        "geography_corrections": [
            "Istiklal Street, Galata Tower and Ortakoy Mosque remain on the European side.",
            "Kuzguncuk is the Asian-side destination.",
            "Nusr-Et Kapalicarsi belongs with the Grand Bazaar/old-city route, not the Asian route.",
        ],
    }
    map_report_path = output / "map-structure-report.json"
    map_report_path.write_text(json.dumps(map_report, ensure_ascii=False, indent=2) + "\n")

    material_entries = []
    for role, collection in (("photo", photos), ("icon", icons)):
        for name, material in collection.items():
            material_entries.append({"asset_id": name, "role": role, **material["manifest"]})
    material_entries.append({"asset_id": "istanbul-osm", "role": "real-map-base", **map_material["manifest"]})
    material_entries.append({"asset_id": "istanbul-osm-d1", "role": "real-map-base", **d1_map_material["manifest"]})
    material_path = output / "material-manifest.json"
    material_path.write_text(json.dumps({"schema_version": 1, "generator": Path(__file__).name, "assets": material_entries}, ensure_ascii=False, indent=2) + "\n")

    report_path = output / "visual-gate-report.json"
    report = run_visual_gates(
        pptx_path,
        pdf_path,
        report_path=report_path,
        render_dir=output / "rendered",
        montage_path=output / "montage.png",
    )
    artifact_manifest = {
        "schema_version": 1,
        "title": spec["title"],
        "source_title": brief.title,
        "input_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
        "input_raw_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "input_hash_canonicalization": "utf-8 text with trailing newlines removed",
        "input_byte_size": len(source_text.encode()),
        "source_trace": trace_path.name,
        "external_source_manifest": evidence_path.name,
        "fact_check_matrix": fact_check_path.name,
        "material_manifest": material_path.name,
        "content_coverage_matrix": coverage_path.name,
        "map_structure_report": map_report_path.name,
        "visual_gate_report": report_path.name,
        "artifacts": {
            path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "byte_size": path.stat().st_size}
            for path in (pptx_path, pdf_path, output / "montage.png")
        },
        "coverage": {
            "airport_and_transport": True,
            "day1_map": True,
            "day2_map_and_geography_correction": True,
            "lodging_from_input": True,
            "food_from_input": True,
            "price_traps": True,
            "photo_spots": True,
        },
        "visual_gate_passed": report["passed"],
        "human_visual_approval": "pending",
        "generated_at": FIXED_TIME,
    }
    (output / "artifact-manifest.json").write_text(json.dumps(artifact_manifest, ensure_ascii=False, indent=2) + "\n")
    return artifact_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/acceptance/istanbul-user-input")
    args = parser.parse_args()
    print(json.dumps(build_package(args.output.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
