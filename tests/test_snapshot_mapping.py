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
    assert "导轨" in slicer["price_reference"]["目标售价"]
    assert "30.6%" in slicer["price_reference"]["预估净利率"]


def test_voc_four_piece_visible_for_previous_gap_products():
    assert "function vocFourPieceBlock" in HTML
    assert "VOC 四件套｜买家原话 / 痛点 / 频次 / 动作" in HTML
    assert DATA["supplement_three_summary"]["voc_four_piece_total"] == 16
    for name in ["酸面包切片器", "口袋孔夹具", "刹车油排气", "番茄支架"]:
        item = find_product(name)
        voc = item.get("voc_evidence") or []
        assert voc, f"missing VOC for {name}"
        row = voc[0]
        assert row.get("买家原话") or row.get("buyer_quote_or_gap")
        assert row.get("痛点主题") or row.get("painpoint_or_need")
        assert row.get("频次/样本量") or row.get("frequency_sample")
        assert row.get("可转化动作") or row.get("expected_feature")


def test_all_products_have_backfilled_core_modules():
    assert DATA["sync_scope"]["matched_items"]["voc"] == 16
    assert DATA["sync_scope"]["matched_items"]["official"] == 16
    assert DATA["sync_scope"]["matched_items"]["supply"] == 16
    assert DATA["sync_scope"]["matched_items"]["profit"] == 16
    assert DATA["sync_scope"]["matched_items"]["definition"] == 16
