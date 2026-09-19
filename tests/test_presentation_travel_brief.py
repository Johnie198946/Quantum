from pathlib import Path

from backend.services.presentation_travel_brief import parse_istanbul_travel_brief


SOURCE = Path("tests/fixtures/presentation/istanbul-source.md")


def test_user_istanbul_source_is_extracted_without_generic_city_rewrite():
    text = SOURCE.read_text(encoding="utf-8")
    brief = parse_istanbul_travel_brief(text)

    assert brief.title.startswith("穷游土耳其？")
    assert len(brief.public_transport_steps) == 3
    assert "M11" in brief.public_transport_steps[2]
    assert "M2" in brief.public_transport_steps[2]
    assert "T1" in brief.public_transport_steps[2]
    assert len(brief.source_day1) == 9
    assert len(brief.source_day2) == 5
    assert [stop.name for stop in brief.source_day1[:4]] == [
        "蓝色清真寺/圣索菲亚大教堂",
        "苏莱曼尼清真寺",
        "İBB Sarayburnu Parkı看海",
        "加拉塔大桥",
    ]
    assert "Seven Hills" in " ".join(brief.lodging)
    assert "Sirkeci Lokantası 1912" in " ".join(brief.food)
    assert "Nusr-Et Steakhouse Kapalıçarşı" in " ".join(brief.food)
    assert "Galata Konak Cafe" in " ".join(brief.food)


def test_d2_is_resequenced_by_real_side_without_losing_source_order():
    brief = parse_istanbul_travel_brief(SOURCE.read_text(encoding="utf-8"))

    assert [stop.name for stop in brief.corrected_day2_europe] == [
        "独立大街",
        "加拉塔石塔",
        "奥塔科伊清真寺",
        "撒盐哥的牛排店 Nusr-Et Steakhouse Kapalıçarşı Nusr-et Sandal Bedesteni",
    ]
    assert [stop.name for stop in brief.corrected_day2_asia] == [
        "库兹衮库克 Kuzguncuk Evleri"
    ]
    assert "欧洲侧" in brief.geography_note
    assert "Kuzguncuk" in brief.geography_note


def test_parser_does_not_invent_additional_hotels_or_restaurants():
    brief = parse_istanbul_travel_brief(SOURCE.read_text(encoding="utf-8"))

    assert len(brief.lodging) == 2
    assert len(brief.food) == 3
    all_recommendations = " ".join((*brief.lodging, *brief.food))
    for unsupported in ("Four Seasons", "Hilton", "Çiya", "Mikla"):
        assert unsupported not in all_recommendations
