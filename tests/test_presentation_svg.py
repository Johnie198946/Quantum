import pytest

from backend.services.presentation_svg import parse_editable_svg


def test_safe_svg_parses_to_editable_primitives_and_adapts_palette():
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
      <rect x="8" y="20" width="48" height="32" fill="#111111"/>
      <circle cx="32" cy="28" r="8" fill="#222222"/>
      <path d="M8 56 L32 40 L56 56 Z" fill="none" stroke="#111111" stroke-width="3"/>
    </svg>"""
    view, primitives = parse_editable_svg(
        svg, palette={"#111111": "#D85A3A", "#222222": "#172A3A"}
    )
    assert view == (0.0, 0.0, 64.0, 64.0)
    assert [primitive.kind for primitive in primitives] == ["rect", "circle", "path"]
    assert primitives[0].fill == "#D85A3A"
    assert len(primitives[2].values) >= 6


@pytest.mark.parametrize(
    "svg,match",
    [
        (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><script/></svg>',
            "unsupported SVG element",
        ),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><path d="M1 1 C2 2 3 3 4 4"/></svg>',
            "unsupported commands",
        ),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><image href="https://example.test/x.png"/></svg>',
            "unsupported SVG element",
        ),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="0" y="0" width="64" height="64" style="fill:red"/></svg>',
            "styling is forbidden",
        ),
    ],
)
def test_editable_svg_fails_closed_for_active_external_or_opaque_content(svg, match):
    with pytest.raises(ValueError, match=match):
        parse_editable_svg(svg)
