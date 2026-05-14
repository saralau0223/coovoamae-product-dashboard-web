import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
DATA = json.loads(re.search(r"const DATA = (.*?);\nlet selected", HTML, re.S).group(1))

DIRECT_RE = re.compile(r"^https://(?:www\.)?amazon\.com/(?:dp|gp/product)/[A-Z0-9]{10}(?:[/?#].*)?$", re.I)
SEARCH_RE = re.compile(r"^https://(?:www\.)?amazon\.com/s\?k=", re.I)


def test_source_data_still_contains_empty_search_and_direct_amazon_urls():
    counts = {"empty": 0, "search": 0, "direct": 0, "other": 0}
    for item in DATA["items"]:
        url = (item.get("amazonUrl") or "").strip()
        if not url:
            counts["empty"] += 1
        elif DIRECT_RE.match(url):
            counts["direct"] += 1
        elif SEARCH_RE.match(url):
            counts["search"] += 1
        else:
            counts["other"] += 1
    assert counts == {"empty": 16, "search": 3, "direct": 7, "other": 0}


def test_amazon_detail_button_is_guarded_by_direct_asin_url_only():
    assert "function amazonLinkInfo" in HTML
    assert "amazon.com/(?:dp|gp/product)/[A-Z0-9]{10}" in HTML
    assert "Amazon搜索参考" in HTML
    assert "待补ASIN直达" in HTML
    assert "aria-disabled" in HTML
    assert "#amazonLink').href = x.amazonUrl || '#'" not in HTML
    assert "updateAmazonLink(x);" in HTML


def test_search_and_empty_urls_are_not_rendered_as_amazon_direct_links():
    assert "textContent = info.label" in HTML
    assert "el.removeAttribute('href')" in HTML
    assert "el.href = info.url" in HTML
    assert "is-search" in HTML
    assert "is-disabled" in HTML
