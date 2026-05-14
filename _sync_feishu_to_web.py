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
    "方舟寻找需求收口",
    "网页新增候选池",
    "网页寻找需求任务队列",
    "Top4补证队列",
    "官方源续补",
    "H10剩余补证",
    "供应链人工验证清单",
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

PRIVATE_HEADERS = {"供应商名称", "供应商链接", "联系人", "联系方式", "备注", "负责人", "token", "key"}
IMAGE_HEADERS = ["imageUrl", "图片URL", "图片url", "图片链接", "主图URL", "主图链接", "H10图片URL", "H10主图URL"]


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


def clean_public_image_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    m = re.search(r"https?://[^\s\"'<>]+", raw)
    if not m:
        return ""
    # Browser-visible images should be public/static URLs only; do not expose signed
    # Feishu attachment URLs or any URL containing credential-like query parameters.
    u = m.group(0).strip()
    if re.search(r"(token|access_token|signature|X-Amz-|Expires=|Authorization=)", u, re.I):
        return ""
    return u


def image_url_from_row(d: Dict[str, str]) -> str:
    for key in IMAGE_HEADERS:
        if d.get(key):
            url = clean_public_image_url(d[key])
            if url:
                return url
    return ""


def apply_image_url(it: Dict[str, Any], d: Dict[str, str]) -> None:
    url = image_url_from_row(d)
    if url:
        it["imageUrl"] = url


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

def parse_priority_label(s: str) -> tuple[str, int]:
    raw = str(s or "").upper()
    if "P0" in raw or "B+" in raw:
        return "B+ 重点补证", 82
    if "P1" in raw or "B-" in raw or "B" in raw:
        return "B 补证", 72
    if "P2" in raw:
        return "C 观察", 60
    return "B 补证", 68


def default_profit() -> Dict[str, Any]:
    return {
        "target_price": 0, "cost_low": 0, "cost_high": 0, "landed_est": 0,
        "referral": 0, "fba_est": 0, "ad_est": 0, "reserve": 0,
        "profit": 0, "margin": 0, "break_even_acos": 0, "quote_target": 0,
        "status": "待报价/待财神爷复算",
    }


def ensure_item_defaults(it: Dict[str, Any]) -> Dict[str, Any]:
    it.setdefault("asin", "")
    it.setdefault("amazonUrl", "")
    it.setdefault("imageUrl", "")
    it.setdefault("price", [])
    it.setdefault("evidence", "")
    it.setdefault("diff", "")
    it.setdefault("risk", "")
    it.setdefault("owner", "总管家分派")
    it.setdefault("decisionSuggestion", "继续补数据")
    it.setdefault("present", [])
    it.setdefault("gaps", [])
    it.setdefault("profit", default_profit())
    it.setdefault("gate", {
        "demand": "待补证", "voc": "待补证", "product": "待定义",
        "supply": "待只读预筛", "finance": "待复算", "next_action": "补齐证据后再决策",
    })
    return it


def ensure_item(items: List[Dict[str, Any]], product: str) -> Dict[str, Any]:
    it = find_item(items, product)
    if not it:
        it = {"product": product}
        items.append(it)
    return ensure_item_defaults(it)


def split_gaps(s: str) -> List[str]:
    raw = re.split(r"[、；;，,]+", str(s or ""))
    return [x.strip() for x in raw if x.strip()][:8]


def parse_price_band(band: str) -> List[float]:
    nums = re.findall(r"(\d+(?:\.\d+)?)", str(band or ""))
    if len(nums) >= 2:
        return [float(nums[0]), float(nums[1])]
    if len(nums) == 1:
        v = float(nums[0]); return [v, v]
    return []


def optional_json(path: str) -> Dict[str, Any]:
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def read_local_followups(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Fold in already-completed Top4 follow-up task outputs when this sync runs on the kanban host.

    The page must show the WEB-A4D43BC96C39 Top4 follow-up evidence, but some child
    workers intentionally produced markdown/json artifacts instead of writing all rows
    back into the master Feishu tabs. These optional reads are read-only and contain
    public/summary fields only; no credentials or supplier contact details are exposed.
    """
    summaries: List[Dict[str, str]] = []

    defs = optional_json("/root/.hermes/kanban/workspaces/t_3b199d67/product_definition_structured.json")
    if defs.get("drafts"):
        summaries.append({
            "模块": "产品定义草案",
            "来源任务": defs.get("task_id", "t_3b199d67"),
            "结果": "酸面包切片器与园艺跪凳各完成1页定义草案；园艺跪凳已设置FBA包装/体积红线和承重测试红线。",
            "缺口/下一步": "仍需ABA/POE/H10 Review、供应商MOQ/包装/食品接触或承重测试验证。",
        })
        for d in defs.get("drafts", []):
            it = ensure_item(items, d.get("direction", ""))
            it["brief"] = {
                "目标用户": "、".join(d.get("target_users", [])),
                "核心场景": "、".join(d.get("core_scenarios", [])),
                "首版规格": json.dumps(d.get("v1_specs", {}), ensure_ascii=False),
                "不要做": "、".join(d.get("avoid", [])),
                "验收标准": d.get("decision", ""),
            }
            it["diff"] = it.get("diff") or "、".join(d.get("must_keep_value_points", []))
            it["risk"] = it.get("risk") or "、".join(d.get("key_risks", []))
            it["gaps"] = list(dict.fromkeys((it.get("gaps") or []) + d.get("evidence_needed", [])))[:10]

    h10 = optional_json("/root/.hermes/kanban/workspaces/t_e4d138df/h10_top4_xray_review_evidence_summary.json")
    if h10.get("directions"):
        summaries.append({
            "模块": "H10 / Black Box / Cerebro",
            "来源任务": "t_e4d138df",
            "结果": "Top4均已补Black Box Keywords、Black Box Products Top20 proxy、Cerebro聚合；酸面包最接近小批量定义，园艺跪凳需求最大但先过体积/承重，口袋孔先过IP/精度，数显扭矩暂缓。",
            "缺口/下一步": "缺真实Xray导出和Review workbook，不能冒充完整Xray/低星原文证据。",
        })
        for v in h10.get("directions", {}).values():
            it = ensure_item(items, v.get("label", ""))
            it.setdefault("h10_evidence", [])
            it["h10_evidence"].append({
                "入口词": f"{v.get('keyword') or v.get('main_keyword','')} SV{v.get('main_sv','')}",
                "销量/收入": f"Top20 proxy ${float(v.get('top20_revenue_usd') or 0):,.0f} / {int(v.get('top20_sales') or 0):,}件",
                "Review门槛": f"median {v.get('review_median','')}；Top5收入占比 {float(v.get('top5_revenue_share') or 0)*100:.1f}%",
                "可粘贴结论/下一步": v.get("small_batch_gate", ""),
            })
            band = parse_price_band(v.get("price_band_usd", ""))
            if band:
                it["price"] = band
            if v.get("top20_revenue_usd"):
                it["evidence"] = (it.get("evidence") or "") + f"｜H10 Top20 proxy收入${float(v.get('top20_revenue_usd'))/1_000_000:.2f}M，销量{int(v.get('top20_sales') or 0):,}，Review median {v.get('review_median')}"
            if "Xray" not in it.get("gaps", []):
                it.setdefault("gaps", []).append("Xray/Review workbook")

    official = optional_json("/root/.hermes/kanban/workspaces/t_7c1ef10d/aba_top4_summary.json")
    # The detailed JSON is large; use compact task-level summary if available.
    if official:
        summaries.append({
            "模块": "官方需求 ABA / POE / SQP / CPC",
            "来源任务": "t_7c1ef10d",
            "结果": "酸面包切片器和园艺跪凳支持继续产品定义但不能直立A类；口袋孔夹具需求成立但Kreg/IP/品牌集中需先过闸门；扭矩扳手需拆规格并验证校准/售后。",
            "缺口/下一步": "POE仅关键词缓存命中、无详情截图/导出；SQP Top4匹配0行；CPC未取得。",
        })

    supply = optional_json("/root/.hermes/kanban/workspaces/t_c5642404/supply_supplier_shortlist.json")
    if supply.get("conclusions"):
        summaries.append({
            "模块": "供应链只读快筛",
            "来源任务": supply.get("task_id", "t_c5642404"),
            "结果": "酸面包手摇目标形态公开MOQ/成本偏高；园艺跪凳供应成熟但FBA体积费与承重测试是硬门。",
            "缺口/下一步": "1688/Alibaba触发风控未绕过；后续需人工登录态核MOQ、包装、食品接触或承重测试。",
        })
        for key, text in supply.get("conclusions", {}).items():
            label = "手摇/手动酸面包切片器" if "sourdough" in key else "园艺跪凳/座椅"
            it = ensure_item(items, label)
            it["supply_readonly_summary"] = text
            it.setdefault("supply_deep", []).append({"状态": "只读快筛完成", "建议": text, "风险": "需人工登录态/正式报价验证，未外联未询价"})
    return summaries


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
            if is_private_header(k):
                continue
            out[k] = d[k]
    return out


def is_private_header(k: str) -> bool:
    lk = str(k).lower()
    return any(h.lower() in lk for h in PRIVATE_HEADERS)


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
        it.pop("owner", None)
        # Rebuilt on every sync from 飞书《补证任务队列》F:J to avoid stale rows.
        it.pop("evidence_tasks", None)
        # Rebuilt on every sync from the three supplement closure sheets.
        it.pop("h10_remaining", None)
        it.pop("official_followup", None)
        it.pop("human_verification", None)

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

    # Discovery / from-zero demand result: 方舟寻找需求收口 + candidate pool.
    discovery_rows: List[Dict[str, str]] = []
    discovery_next_steps: List[Dict[str, str]] = []
    discovery_updated = ""
    discovery_request_id = ""
    discovery_conclusion = ""
    ark_vals = fetched.get("主表/方舟寻找需求收口", [])
    if len(ark_vals) > 1:
        discovery_updated = cell_text(ark_vals[1][0]).replace("更新时间：", "") if len(ark_vals[1]) > 0 else ""
        discovery_request_id = cell_text(ark_vals[1][1]).replace("请求ID：", "") if len(ark_vals[1]) > 1 else ""
        discovery_conclusion = cell_text(ark_vals[1][2]).replace("结论：", "") if len(ark_vals[1]) > 2 else ""
    for d in rows_by_header(ark_vals, 2):
        product = d.get("产品方向", "")
        if not product:
            if d.get("请求ID") == "下一步" or d.get("排名") in {"P0", "P1", "P2"}:
                discovery_next_steps.append(d)
            continue
        rank_text = d.get("排名", "")
        if not str(rank_text).isdigit():
            if d.get("请求ID") == "下一步":
                discovery_next_steps.append(d)
            continue
        rank = int(float(rank_text))
        level, score = parse_priority_label(d.get("优先级", ""))
        it = ensure_item(items, product)
        apply_image_url(it, d)
        it.update({
            "rank": rank,
            "level": level,
            "score": score,
            "product": product,
            "evidence": d.get("关键证据", it.get("evidence", "")),
            "diff": d.get("差异化假设", it.get("diff", "")),
            "risk": d.get("需要补证", it.get("risk", "")),
            "owner": "方舟 → 产品开发/鹰眼/H10/VOC/供应链只读补证",
            "decisionSuggestion": ("补数据后进入产品定义" if "是" in d.get("是否进入产品定义", "") else "暂缓观察"),
            "discovery_source": clean_public_dict(d, ["请求ID", "排名", "优先级", "产品方向", "候选池状态", "一句话机会", "目标用户", "差异化假设", "关键证据", "需要补证", "是否进入产品定义"] + IMAGE_HEADERS),
        })
        it["gaps"] = split_gaps(d.get("需要补证", ""))
        it["present"] = list(dict.fromkeys((it.get("present") or []) + ["H10", "VOC", "ABA" if "ABA" in d.get("关键证据", "") else "市场初筛"]))
        it["gate"].update({
            "demand": "已初筛，待补官方/H10闭环",
            "voc": "有初筛痛点，待Review原文",
            "product": "进入产品定义" if "是" in d.get("是否进入产品定义", "") else "观察池",
            "supply": "只读快筛/待验证",
            "finance": "待财神爷复算",
            "next_action": d.get("是否进入产品定义", "") or d.get("候选池状态", ""),
        })
        discovery_rows.append(it["discovery_source"])

    candidate_pool_rows = [clean_public_dict(d, ["提交时间", "产品/关键词/链接", "补充说明", "优先级", "来源", "状态", "下一步负责人", "方舟处理记录", "创建方式", "请求ID"]) for d in rows_by_header(fetched.get("主表/网页新增候选池", []), 0) if d.get("产品/关键词/链接")]
    discovery_queue_rows = [clean_public_dict(d, ["提交时间", "寻找范围/主题", "补充约束", "优先级", "来源", "当前阶段", "状态", "鹰眼任务ID", "H10任务ID", "VOC任务ID", "猫头鹰任务ID", "方舟汇总任务ID"]) for d in rows_by_header(fetched.get("主表/网页寻找需求任务队列", []), 0) if d.get("寻找范围/主题")]
    top4_backfill_queue = [clean_public_dict(d, ["优先级", "产品方向", "补证类型", "负责人建议", "具体动作", "验收标准", "权限边界"]) for d in rows_by_header(fetched.get("主表/Top4补证队列", []), 0) if d.get("产品方向")]

    followup_summaries = read_local_followups(items)
    discovery_result = {
        "request_id": discovery_request_id,
        "updated_at": discovery_updated,
        "conclusion": discovery_conclusion,
        "top10": discovery_rows[:10],
        "top4": discovery_rows[:4],
        "next_steps": discovery_next_steps[:10],
        "candidate_pool_rows": candidate_pool_rows[:20],
        "discovery_queue_rows": discovery_queue_rows[:10],
        "top4_backfill_queue": top4_backfill_queue[:20],
        "followup_summaries": followup_summaries,
    }

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
            apply_image_url(it, d)
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
            # Do not expose owner/person fields on the public static page.

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
            public = {k: v for k, v in d.items() if not is_private_header(k) and v}
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

    # New supplement closure sheets written by specialist agents.
    # Expose only public status/evidence/checklist fields; keep supplier identities,
    # private links and any writeback credentials out of the browser dataset.
    h10_remaining_rows: List[Dict[str, str]] = []
    for d in rows_by_header(fetched.get("主表/H10剩余补证", []), 0):
        product = d.get("产品") or ""
        if not product or product.startswith("写回时间"):
            continue
        public = clean_public_dict(d, [
            "产品", "补什么", "入口词", "ASIN", "imageUrl", "价格", "月销额", "Review", "BSR", "相关性判断", "仍缺字段"
        ])
        if not public:
            continue
        h10_remaining_rows.append(public)
        it = find_item(items, product)
        if it:
            it.setdefault("h10_remaining", []).append({k: v for k, v in public.items() if k != "产品"})

    official_followup_rows: List[Dict[str, str]] = []
    for d in rows_by_header(fetched.get("主表/官方源续补", []), 0):
        product = d.get("产品") or ""
        if not product:
            continue
        public = clean_public_dict(d, ["产品", "缺口", "能否补到", "证据/失败原因", "下一步", "是否需要人工权限"])
        if not public:
            continue
        official_followup_rows.append(public)
        it = find_item(items, product)
        if it:
            it.setdefault("official_followup", []).append({k: v for k, v in public.items() if k != "产品"})

    human_verification_rows: List[Dict[str, str]] = []
    human_verification_latest = ""
    for d in rows_by_header(fetched.get("主表/供应链人工验证清单", []), 0):
        product = d.get("产品方向") or d.get("产品") or ""
        if not product:
            continue
        public = clean_public_dict(d, [
            "优先级", "产品方向", "未闭环字段", "当前F:J状态", "最新补证结果", "闭环判断", "只读验证清单", "人工登录/页面截图需核字段", "建议负责人/动作", "来源任务/证据", "更新时间", "执行边界"
        ])
        if not public:
            continue
        human_verification_rows.append(public)
        if public.get("更新时间") and public["更新时间"] > human_verification_latest:
            human_verification_latest = public["更新时间"]
        it = find_item(items, product)
        if it:
            it.setdefault("human_verification", []).append({k: v for k, v in public.items() if k != "产品方向"})

    def count_rows(rows: List[Dict[str, str]], *needles: str) -> int:
        return sum(1 for r in rows if any(n in " ".join(r.values()) for n in needles))

    supplement_three_summary = {
        "h10_remaining_total": len(h10_remaining_rows),
        "h10_fields_completed": count_rows(h10_remaining_rows, "已补"),
        "h10_still_missing": count_rows(h10_remaining_rows, "仍缺"),
        "official_followup_total": len(official_followup_rows),
        "official_unclosed": count_rows(official_followup_rows, "未补", "不闭环", "缺口"),
        "official_manual_required": sum(1 for r in official_followup_rows if "是" in r.get("是否需要人工权限", "")),
        "human_verification_total": len(human_verification_rows),
        "human_verification_p0": sum(1 for r in human_verification_rows if r.get("优先级") == "P0"),
        "latest_update": max([evidence_queue_latest, human_verification_latest, ""]),
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
    # Keep the interactive product list aligned with the latest Ark Top10 ranking.
    # The historical DailyTop10 tab can still contain older ranked rows; demote them so
    # WEB-A4D43BC96C39 Top10 is the default visible pool after sync.
    discovery_norms = {norm(r.get("产品方向", "")) for r in discovery_rows if r.get("产品方向")}
    for it in items:
        if discovery_norms and norm(it.get("product", "")) not in discovery_norms and int(it.get("rank") or 999) <= 20:
            it["rank"] = 100 + int(it.get("rank") or 0)
            it["level"] = it.get("level") or "历史候选"
    for r in discovery_rows:
        product = r.get("产品方向", "")
        if not product:
            continue
        it = ensure_item(items, product)
        try:
            it["rank"] = int(float(r.get("排名") or 999))
        except Exception:
            pass
        level, score = parse_priority_label(r.get("优先级", ""))
        it["level"] = level
        it["score"] = score
        it["decisionSuggestion"] = ("补数据后进入产品定义" if "是" in r.get("是否进入产品定义", "") else "暂缓观察")
    items.sort(key=lambda x: (int(x.get("rank") or 999), str(x.get("product") or "")))

    new_data = {
        "updated_at": source_stamp or now,
        "web_synced_at": now,
        "sheet_url": MAIN_URL,
        "human_supply_url": SUP_URL,
        "evidence_queue_url": MAIN_URL,
        "evidence_queue_updated_at": evidence_queue_latest,
        "evidence_queue_summary": evidence_queue_summary,
        "evidence_queue_rows": evidence_queue_rows[:80],
        "h10_remaining_rows": h10_remaining_rows[:80],
        "official_followup_rows": official_followup_rows[:80],
        "human_verification_rows": human_verification_rows[:80],
        "supplement_three_summary": supplement_three_summary,
        "discovery_result": discovery_result,
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
    page_version = f"{now}｜飞书最新展示字段同步｜手机端紧凑优化"
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
        "h10_remaining_total": supplement_three_summary["h10_remaining_total"],
        "official_followup_total": supplement_three_summary["official_followup_total"],
        "official_manual_required": supplement_three_summary["official_manual_required"],
        "human_verification_total": supplement_three_summary["human_verification_total"],
        "supplement_three_latest_update": supplement_three_summary["latest_update"],
        "discovery_top10": len(discovery_result.get("top10", [])),
        "discovery_followups": len(discovery_result.get("followup_summaries", [])),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
