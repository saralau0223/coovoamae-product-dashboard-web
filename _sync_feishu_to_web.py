#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

MAIN_SPREADSHEET = "JMW5sATAkhxy8DtTGsAcyesdnOc"
SUP_SPREADSHEET = "Se6OsbdbIhq73TtbQCPckIPrnsg"
MAIN_URL = f"https://bcn9zhmj0ib7.feishu.cn/sheets/{MAIN_SPREADSHEET}"
SUP_URL = f"https://bcn9zhmj0ib7.feishu.cn/sheets/{SUP_SPREADSHEET}"
ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
DATA_JSON = ROOT / "product_dashboard_web_data.json"

MAIN_TABS = [
    "每日Top10推荐",
    "市场竞争方舟总结",
    "Top4产品定义Brief",
    "Top4询价规格",
    "供应链深度巡查",
    "价格参考利润预估",
    "供应商询价回传表",
    "样品采购跟进表",
    "Top4H10补证",
    "Top4VOC补证",
    "Top4官方需求补证",
    "补证任务队列",
]
SUP_TABS = ["需要找供应商的产品表", "采样记录表"]

PRIVATE_HEADERS = {"供应商名称", "供应商链接", "联系人/备注", "供应商名称/链接", "负责人"}


def token() -> str:
    app_id = os.getenv("FEISHU_APP_ID") or os.getenv("LARK_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET") or os.getenv("LARK_APP_SECRET")
    if not app_id or not app_secret:
        raise RuntimeError("missing Feishu app credentials")
    j = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=25,
    ).json()
    if j.get("code") != 0:
        raise RuntimeError(f"Feishu token failed: {j.get('code')} {j.get('msg')}")
    return j["tenant_access_token"]


def headers(tok: str) -> Dict[str, str]:
    return {"Authorization": "Bearer " + tok, "Content-Type": "application/json; charset=utf-8"}


def sheets(h: Dict[str, str], spreadsheet: str) -> Dict[str, Dict[str, Any]]:
    j = requests.get(
        f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{spreadsheet}/sheets/query",
        headers=h,
        timeout=30,
    ).json()
    if j.get("code") != 0:
        raise RuntimeError(f"query sheets failed: {spreadsheet} {j}")
    return {s["title"]: s for s in j.get("data", {}).get("sheets", [])}


def values(h: Dict[str, str], spreadsheet: str, sheet_id: str, rng: str = "A1:AZ200") -> List[List[Any]]:
    j = requests.get(
        f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet}/values/{sheet_id}!{rng}",
        headers=h,
        timeout=45,
    ).json()
    if j.get("code") != 0:
        raise RuntimeError(f"values failed: {spreadsheet} {sheet_id} {j}")
    return j.get("data", {}).get("valueRange", {}).get("values", []) or []


def cell_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        parts = []
        for x in v:
            if isinstance(x, dict):
                # Keep URL text/link only when it is the actual cell value; no cookies/tokens are exposed.
                parts.append(str(x.get("text") or x.get("link") or "").strip())
            else:
                parts.append(cell_text(x))
        return " ".join(p for p in parts if p).strip()
    if isinstance(v, dict):
        if v.get("type") == "embed-image":
            return ""
        return str(v.get("text") or v.get("link") or "").strip()
    return str(v).strip()


def rows_by_header(vals: List[List[Any]], header_idx: int) -> List[Dict[str, str]]:
    if len(vals) <= header_idx:
        return []
    raw_header = [cell_text(c) for c in vals[header_idx]]
    out: List[Dict[str, str]] = []
    for row in vals[header_idx + 1 :]:
        d: Dict[str, str] = {}
        nonempty = False
        for i, h in enumerate(raw_header):
            if not h:
                continue
            val = cell_text(row[i]) if i < len(row) else ""
            if val:
                nonempty = True
            d[h] = val
        if nonempty:
            out.append(d)
    return out


def norm(s: str) -> str:
    s = str(s or "").lower()
    s = re.sub(r"asin[:：]\s*[a-z0-9]+", "", s)
    s = re.sub(r"样本[:：].*", "", s, flags=re.S)
    s = re.sub(r"[\s\n\r\t|｜/、:：()（）\-+]+", "", s)
    return s


def product_name_from_daily(cell: str) -> str:
    return str(cell or "").split("\n")[0].strip()


def asin_from_text(s: str) -> str:
    m = re.search(r"\b(B0[A-Z0-9]{8})\b", str(s or ""), re.I)
    return m.group(1).upper() if m else ""


def parse_rank_score(s: str) -> tuple[Optional[int], str, Optional[int]]:
    rank = None
    score = None
    m = re.search(r"#\s*(\d+)", s or "")
    if m:
        rank = int(m.group(1))
    m = re.search(r"(\d+)\s*分", s or "")
    if m:
        score = int(m.group(1))
    level = ""
    if "A" in (s or ""):
        level = "A 直接推进"
    elif "B" in (s or ""):
        level = "B 补证"
    elif "C" in (s or ""):
        level = "C 备选"
    return rank, level, score


def find_item(items: List[Dict[str, Any]], product: str) -> Optional[Dict[str, Any]]:
    if not product:
        return None
    np = norm(product)
    if not np:
        return None
    best = None
    best_score = 0
    for it in items:
        ni = norm(it.get("product", ""))
        if not ni:
            continue
        score = 0
        if np == ni:
            score = 100
        elif np in ni or ni in np:
            score = min(len(np), len(ni))
        else:
            # Token-ish CJK prefix overlap.
            for n in range(min(len(np), len(ni)), 3, -1):
                if np[:n] == ni[:n]:
                    score = n
                    break
        if score > best_score:
            best, best_score = it, score
    return best if best_score >= 4 else None


def clean_public_dict(d: Dict[str, str], keep: List[str]) -> Dict[str, str]:
    out = {}
    for k in keep:
        if k in d and d.get(k):
            if k in PRIVATE_HEADERS:
                continue
            out[k] = d[k]
    return out


def is_example_row(d: Dict[str, str]) -> bool:
    joined = " ".join(d.values())
    return any(x in joined for x in ["示例", "example.com", "Q-示例", "S-示例"])


def main() -> None:
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r"const DATA = (.*?);\nlet selected", html, re.S)
    if not m:
        raise RuntimeError("Cannot locate DATA in index.html")
    old_data = json.loads(m.group(1))
    items: List[Dict[str, Any]] = old_data.get("items", [])
    # Remove browser-visible writeback tokens/keys from existing dataset.
    for it in items:
        it.pop("supplyToken", None)
        it.pop("supplyKey", None)
        # Rebuilt on every sync from 飞书《补证任务队列》F:J to avoid stale rows.
        it.pop("evidence_tasks", None)

    tok = token()
    h = headers(tok)
    main_sheets = sheets(h, MAIN_SPREADSHEET)
    sup_sheets = sheets(h, SUP_SPREADSHEET)

    fetched: Dict[str, List[List[Any]]] = {}
    missing: List[str] = []
    for t in MAIN_TABS:
        if t not in main_sheets:
            missing.append("主表/" + t)
            continue
        fetched["主表/" + t] = values(h, MAIN_SPREADSHEET, main_sheets[t]["sheet_id"])
    for t in SUP_TABS:
        if t not in sup_sheets:
            missing.append("人工简表/" + t)
            continue
        fetched["人工简表/" + t] = values(h, SUP_SPREADSHEET, sup_sheets[t]["sheet_id"])

    # Daily Top10 core fields.
    top_vals = fetched.get("主表/每日Top10推荐", [])
    source_stamp = ""
    if top_vals and len(top_vals[0]) > 8:
        source_stamp = cell_text(top_vals[0][8])
    if top_vals:
        for d in rows_by_header(top_vals, 2):
            pname = product_name_from_daily(d.get("产品方向/样本", ""))
            it = find_item(items, pname)
            if not it:
                continue
            rank, level, score = parse_rank_score(d.get("等级", ""))
            if rank:
                it["rank"] = rank
            if level:
                # Keep more precise old label if it already has useful sub-label.
                it.setdefault("level", level)
            if score:
                it["score"] = score
            if pname:
                it["product"] = pname
            asin = asin_from_text(d.get("产品方向/样本", ""))
            if asin:
                it["asin"] = asin
                it["amazonUrl"] = f"https://www.amazon.com/dp/{asin}"
            if d.get("需求证据"):
                it["evidence"] = d["需求证据"]
            if d.get("差异化"):
                it["diff"] = d["差异化"]
            if d.get("风险"):
                it["risk"] = d["风险"]
            if d.get("下一步") or d.get("下一步/负责人"):
                it["owner"] = d.get("下一步") or d.get("下一步/负责人")

    # Market / competition / Ark.
    for d in rows_by_header(fetched.get("主表/市场竞争方舟总结", []), 0):
        it = find_item(items, d.get("产品", ""))
        if not it:
            continue
        it["market_competition"] = clean_public_dict(d, [
            "市场规模快照", "市场规模说明", "竞争分析快照", "竞争分析说明", "利润快照", "方舟建议总结", "下一棒", "主要缺口", "更新时间"
        ])
        if d.get("方舟建议总结"):
            it["decisionSuggestion"] = d["方舟建议总结"]

    # Product Brief.
    for d in rows_by_header(fetched.get("主表/Top4产品定义Brief", []), 0):
        it = find_item(items, d.get("产品", ""))
        if it:
            it["brief"] = clean_public_dict(d, ["目标用户", "核心场景", "核心痛点", "功能组合", "不要做", "首版规格", "图片卖点", "验收标准"])

    # Inquiry specs.
    for d in rows_by_header(fetched.get("主表/Top4询价规格", []), 0):
        it = find_item(items, d.get("产品", ""))
        if it:
            it["inquiry_spec"] = clean_public_dict(d, ["询价规格草案", "必须问供应商", "样品要求", "交期/MOQ字段", "质检重点", "报价验收口径"])

    # Deep patrol and reference profit (skip templates/examples).
    for d in rows_by_header(fetched.get("主表/供应链深度巡查", []), 0):
        if is_example_row(d):
            continue
        it = find_item(items, d.get("产品", ""))
        if it:
            it.setdefault("supply_deep", []).append(clean_public_dict(d, [
                "产品", "平台", "产品一致性", "供应商质量", "参考单价", "MOQ", "包装/重量", "认证/质检", "匹配评分", "利润预估用价", "风险", "建议", "状态", "更新时间"
            ]))
    for d in rows_by_header(fetched.get("主表/价格参考利润预估", []), 0):
        if is_example_row(d):
            continue
        it = find_item(items, d.get("产品", ""))
        if it:
            it["price_reference"] = clean_public_dict(d, [
                "目标售价", "目标到岸成本红线", "供应链参考价区间", "利润预估用价", "预估FBA/体积费", "佣金", "广告预留", "退货损耗", "预估净利", "预估净利率", "盈亏平衡ACoS", "结论", "需财神爷复算字段", "更新时间"
            ])

    # Formal quote feedback (skip private contact/link fields).
    for d in rows_by_header(fetched.get("主表/供应商询价回传表", []), 1):
        if is_example_row(d):
            continue
        it = find_item(items, d.get("产品方向", ""))
        if it:
            it.setdefault("formal_quotes", []).append(clean_public_dict(d, [
                "询价ID", "产品方向", "询价状态", "平台/来源", "产品一致性", "供应商优质度", "匹配度评分(1-5)", "报价币种", "贸易条款(EXW/FOB/DDP)", "MOQ", "100pcs单价", "500pcs单价", "1000pcs单价", "样品费", "样品运费", "打样周期", "大货交期", "包装尺寸", "单件重量", "外箱信息", "材质/工艺", "认证/风险备注", "主要风险"
            ]))

    # Main sample tracking.
    for d in rows_by_header(fetched.get("主表/样品采购跟进表", []), 1):
        if is_example_row(d):
            continue
        it = find_item(items, d.get("产品方向", ""))
        if it:
            it.setdefault("sample_followups", []).append(clean_public_dict(d, [
                "样品ID", "关联询价ID", "产品方向", "样品采购状态", "刘希确认记录", "样品费", "运费", "付款状态", "下单日期", "发货日期", "预计到达", "实际到达", "样品一致性", "做工评分(1-5)", "功能评分(1-5)", "包装评分(1-5)", "问题记录", "样品结论", "下一步动作", "看板同步状态"
            ]))

    # Evidence补证 rows.
    for key, field, header_idx in [
        ("主表/Top4H10补证", "h10_evidence", 0),
        ("主表/Top4VOC补证", "voc_evidence", 0),
        ("主表/Top4官方需求补证", "official_evidence", 0),
    ]:
        grouped: Dict[str, List[Dict[str, str]]] = {}
        for d in rows_by_header(fetched.get(key, []), header_idx):
            product = d.get("产品") or d.get("product")
            it = find_item(items, product)
            if not it:
                continue
            # Limit to first 6 per source to keep page light.
            public = {k: v for k, v in d.items() if k not in PRIVATE_HEADERS and v}
            grouped.setdefault(it["product"], []).append(public)
        for it in items:
            if grouped.get(it.get("product", "")):
                it[field] = grouped[it["product"]][:6]

    # Supplement task queue status from 飞书《补证任务队列》F:J.
    # Only expose public status/result/judgement/source/update fields; no credentials or write tokens.
    evidence_queue_rows: List[Dict[str, str]] = []
    evidence_queue_latest = ""
    for d in rows_by_header(fetched.get("主表/补证任务队列", []), 1):
        product = d.get("产品方向") or d.get("产品") or ""
        gap = d.get("补什么") or ""
        if not product or not gap:
            continue
        public = clean_public_dict(d, ["补什么", "状态", "最新补证结果", "闭环判断", "来源任务/证据", "更新时间"])
        if not public:
            continue
        # Keep product name only for global summary matching/display.
        row = {"产品方向": product, **public}
        evidence_queue_rows.append(row)
        if row.get("更新时间") and row["更新时间"] > evidence_queue_latest:
            evidence_queue_latest = row["更新时间"]
        it = find_item(items, product)
        if it:
            it.setdefault("evidence_tasks", []).append(public)

    def count_queue_status(pattern: str) -> int:
        return sum(1 for r in evidence_queue_rows if pattern in (r.get("状态", "") + r.get("闭环判断", "")))

    evidence_queue_summary = {
        "total": len(evidence_queue_rows),
        "partial": count_queue_status("部分补证"),
        "unclosed": count_queue_status("未闭环"),
        "manual_verify": count_queue_status("待人工验证"),
        "not_updated": count_queue_status("未更新"),
        "latest_update": evidence_queue_latest,
    }

    # Human supply simple table.
    for d in rows_by_header(fetched.get("人工简表/需要找供应商的产品表", []), 1):
        if not d.get("产品ID") or not d.get("需要找供应商的产品"):
            continue
        it = find_item(items, d.get("需要找供应商的产品", ""))
        if it:
            # Show quote/MOQ summaries only; no supplier identity/link columns.
            it["human_supply"] = clean_public_dict(d, [
                "产品ID", "优先级", "需要找供应商的产品", "参考ASIN", "目标售价", "到岸成本红线", "要找什么/关键规格", "开发要求", "开发状态", "供应商1报价/MOQ", "供应商2报价/MOQ", "供应商3报价/MOQ", "包装重量/尺寸", "认证/风险备注", "是否建议采样"
            ])

    # Human sampling simple table.
    for d in rows_by_header(fetched.get("人工简表/采样记录表", []), 1):
        if not d.get("样品ID") or not d.get("产品"):
            continue
        it = find_item(items, d.get("产品", ""))
        if it:
            it.setdefault("human_samples", []).append(clean_public_dict(d, [
                "样品ID", "关联产品ID", "产品", "样品状态", "样品费", "运费", "下单日期", "预计到达", "实际到达", "一致性评分(1-5)", "做工评分(1-5)", "功能评分(1-5)", "包装评分(1-5)", "问题记录", "样品结论", "下一步"
            ]))

    cst = timezone(timedelta(hours=8))
    now = datetime.now(cst).strftime("%Y-%m-%d %H:%M CST")
    new_data = {
        "updated_at": source_stamp or now,
        "web_synced_at": now,
        "sheet_url": MAIN_URL,
        "human_supply_url": SUP_URL,
        "evidence_queue_url": MAIN_URL,
        "evidence_queue_updated_at": evidence_queue_latest,
        "evidence_queue_summary": evidence_queue_summary,
        "evidence_queue_rows": evidence_queue_rows[:80],
        "sync_scope": {
            "checked_main_tabs": MAIN_TABS,
            "checked_human_tabs": SUP_TABS,
            "missing_tabs": missing,
        },
        "items": sorted(items, key=lambda x: int(x.get("rank") or 999)),
    }

    old_json = DATA_JSON.read_text(encoding="utf-8") if DATA_JSON.exists() else ""
    new_json = json.dumps(new_data, ensure_ascii=False, indent=2, sort_keys=True)
    changed = old_json.strip() != new_json.strip()

    DATA_JSON.write_text(new_json + "\n", encoding="utf-8")
    compact = json.dumps(new_data, ensure_ascii=False, separators=(",", ":"))
    # Use function replacements: re.sub replacement strings interpret backslashes
    # (for example JSON "\n") and can corrupt embedded JSON into invalid JS.
    html2 = re.sub(
        r"const DATA = .*?;\nlet selected",
        lambda _m: "const DATA = " + compact + ";\nlet selected",
        html,
        count=1,
        flags=re.S,
    )
    page_version = f"{now}｜飞书最新展示字段同步"
    html2 = re.sub(
        r"const PAGE_VERSION='[^']*';",
        lambda _m: "const PAGE_VERSION='" + page_version + "';",
        html2,
        count=1,
    )
    INDEX.write_text(html2, encoding="utf-8")

    summary = {
        "changed": changed,
        "web_synced_at": now,
        "items": len(new_data["items"]),
        "missing_tabs": missing,
        "main_tabs_checked": len(MAIN_TABS),
        "human_tabs_checked": len(SUP_TABS),
        "items_with_human_supply": sum(1 for x in items if x.get("human_supply")),
        "items_with_deep_patrol": sum(1 for x in items if x.get("supply_deep")),
        "items_with_formal_quotes": sum(1 for x in items if x.get("formal_quotes")),
        "items_with_samples": sum(1 for x in items if x.get("sample_followups") or x.get("human_samples")),
        "evidence_queue_total": evidence_queue_summary["total"],
        "evidence_queue_partial": evidence_queue_summary["partial"],
        "evidence_queue_unclosed": evidence_queue_summary["unclosed"],
        "evidence_queue_manual_verify": evidence_queue_summary["manual_verify"],
        "evidence_queue_latest_update": evidence_queue_latest,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
