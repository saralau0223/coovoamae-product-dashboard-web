import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
DATA = json.loads(re.search(r"const DATA = (.*?);\nlet selected", HTML, re.S).group(1))


def find_product(name):
    for item in DATA["items"]:
        if name in item.get("product", ""):
            return item
    raise AssertionError(f"product not found: {name}")


def test_snapshots_read_market_competition_and_profit_fallback_helpers():
    assert "fieldFromText(t.market" in HTML
    assert "profitSnapshot(x)" in HTML
    assert "price_reference/财神爷摘要" in HTML
    assert "el.innerHTML=[marketSnapshot(x),profitSnapshot(x),competitionSnapshot(x)]" in HTML


def test_acceptance_seed_values_exist_in_data_source():
    garden = find_product("园艺跪凳")
    garden_text = json.dumps(garden.get("market_competition"), ensure_ascii=False)
    assert "$1.153M" in garden_text
    assert "22,242" in garden_text
    assert "$33.90-$79.99" in garden_text
    assert "1128" in garden_text
    assert "Top3 26% / Top5 40%" in garden_text
    assert garden["profit"]["margin"] == 21.1
    assert garden["profit"]["break_even_acos"] == 36.1

    slicer = find_product("酸面包切片器")
    slicer_text = json.dumps(slicer.get("market_competition"), ensure_ascii=False)
    assert "$1.352M" in slicer_text
    assert "26,455" in slicer_text
    assert "$29.99-$69.99" in slicer_text
    assert "633" in slicer_text
    assert slicer["profit"]["target_price"] == 0
    assert slicer["price_reference"]["目标售价"] == "$54.99"
    assert slicer["price_reference"]["预估净利率"] == "18.9%"
