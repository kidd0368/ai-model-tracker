#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 模型情報站 - 靜態網站產生器 + AES-256-GCM 加密
用法: SITE_PASSWORD='...' python3 build.py
輸出: index.html (加密殼頁) + data.enc (加密資料備份)
"""
import json, os, sys, base64, html, math, tempfile
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from validate_data import validate_or_raise

ROOT = os.path.dirname(os.path.abspath(__file__))
PASSWORD = os.environ.get("SITE_PASSWORD") or (sys.argv[1] if len(sys.argv) > 1 else None)
if not PASSWORD:
    sys.exit("ERROR: 請以 SITE_PASSWORD 環境變數提供密碼")
ITER = 300000

def esc(s):
    return html.escape(str(s), quote=False)

def encrypt(plaintext: bytes) -> dict:
    salt = os.urandom(16)
    iv = os.urandom(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER)
    key = kdf.derive(PASSWORD.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, plaintext, None)
    return {
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(iv).decode(),
        "ct": base64.b64encode(ct).decode(),
        "iter": ITER,
    }

with open(os.path.join(ROOT, "data.json"), encoding="utf-8") as f:
    D = json.load(f)
validate_or_raise(D)

# ---------- 渲染內容頁 ----------
def render_daily_log():
    out = []
    for day in D["daily_log"]:
        items = "".join(
            f'<li><span class="tag">{esc(i["cat"])}</span> {esc(i["text"])}'
            + (f' <a href="{html.escape(i["url"], quote=True)}" target="_blank" rel="noopener">來源↗</a>' if i.get("url") else "")
            + "</li>"
            for i in day["items"]
        )
        out.append(f'<div class="card"><h3>{esc(day["date"])}｜{esc(day["title"])}</h3><ul class="log">{items}</ul></div>')
    return "".join(out)

def render_section_updates(section):
    events = D.get("section_updates", {}).get(section, [])
    if not events:
        return ""
    items = []
    for event in events[:20]:
        link = ""
        if event.get("url"):
            link = (
                f' <a href="{html.escape(event["url"], quote=True)}" '
                'target="_blank" rel="noopener">來源↗</a>'
            )
        source = f'｜{esc(event["source"])}' if event.get("source") else ""
        items.append(
            f'<li><span class="tag">{esc(event.get("cat", "產業"))}</span> '
            f'{esc(event["text"])}{link}<small>{esc(event.get("date", ""))}{source}</small></li>'
        )
    return '<div class="card auto-update"><h3>最新自動更新</h3><ul class="log">' + "".join(items) + "</ul></div>"

def table(headers, rows_html):
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    return f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead><tbody>{rows_html}</tbody></table></div>'

SOURCE_TYPE_LABELS = {
    "company_disclosure": "公司披露",
    "media_report": "媒體報導",
    "third_party_estimate": "第三方估算",
    "third_party_sample": "第三方樣本",
    "third_party_benchmark": "第三方評測",
    "attachment_synthesis": "附件綜合整理",
}

def fmt_number(value, digits=1):
    rendered = f"{value:.{digits}f}"
    if digits == 0:
        return rendered
    return rendered.rstrip("0").rstrip(".")

def fmt_signed(value, digits=1):
    prefix = "+" if value > 0 else ""
    return prefix + fmt_number(value, digits)

def arr_display_with_unit(display):
    rendered = str(display).strip()
    if any(unit in rendered for unit in ("億", "美元", "US$")):
        return rendered
    return f"{rendered} 億美元"

def arr_currency_display(display):
    rendered = str(display).strip()
    for qualifier in (">=", "<=", ">", "<", "≥", "≤", "≈", "~"):
        if rendered.startswith(qualifier):
            return f"{qualifier}${rendered[len(qualifier):]}億"
    return f"${rendered}億"

def source_badge(source_type):
    label = SOURCE_TYPE_LABELS.get(source_type, source_type)
    css_class = str(source_type).replace("_", "-")
    return f'<span class="source-badge {html.escape(css_class, quote=True)}">{esc(label)}</span>'

def source_link(source, url=None):
    label = esc(source)
    if not url:
        return label
    safe_url = html.escape(url, quote=True)
    return f'<a href="{safe_url}" target="_blank" rel="noopener">{label}↗</a>'

def month_index(month):
    year, month_number = map(int, month.split("-"))
    return year * 12 + month_number

def render_arr_expectations():
    comparison = D.get("arr_series", {}).get("expectation_comparison")
    if not comparison:
        return ""
    latest = comparison["latest"]
    latest_value = latest["value"]
    latest_display = latest.get("display") or f'{latest.get("qualifier", "")}{fmt_number(latest_value)}'
    rows = [
        f'<tr><td><b>{esc(latest["label"])}</b><small>{esc(comparison["as_of"])}</small></td>'
        f'<td class="num"><b>{esc(arr_display_with_unit(latest_display))}</b></td>'
        f'<td>{source_badge(latest["source_type"])} {source_link(latest["source"], latest.get("url"))}</td>'
        f'<td>{esc(latest["note"])}</td></tr>'
    ]
    for expectation in comparison["expectations"]:
        gap = latest_value - expectation["value"]
        gap_pct = gap / expectation["value"] * 100
        rows.append(
            f'<tr><td><b>{esc(expectation["label"])}</b><small>{esc(expectation["as_of"])}</small></td>'
            f'<td class="num">{fmt_number(expectation["value"])} 億美元</td>'
            f'<td>{source_badge(expectation["source_type"])} '
            f'{source_link(expectation["source"], expectation.get("url"))}</td>'
            f'<td class="num">以 {fmt_number(latest_value)} 億下限：{fmt_number(gap, 0)} 億 '
            f'（{gap_pct:.1f}%）</td></tr>'
        )
    return (
        f'<div class="card"><h3>{esc(comparison["title"])}</h3>'
        + table(["口徑", "ARR / run-rate", "來源層級", "與最新報導下限比較"], "".join(rows))
        + f'<p class="desc calc-note">{esc(comparison["note"])}</p></div>'
    )

def render_arr_momentum():
    momentum = D.get("arr_series", {}).get("momentum")
    if not momentum:
        return ""
    points = momentum["points"]
    rows = []
    intervals = []
    for index, point in enumerate(points):
        display = f'{point.get("qualifier", "")}{fmt_number(point["v"], 2)}'
        if index == 0:
            rows.append(
                f'<tr><td>{esc(point["d"])}<small>{esc(point["label"])}</small></td>'
                f'<td class="num"><b>{esc(display)} 億</b></td>'
                '<td colspan="6" class="muted-cell">起始觀測</td>'
                f'<td>{source_badge(point["source_type"])} {esc(point["source"])}</td></tr>'
            )
            continue
        previous = points[index - 1]
        months = month_index(point["d"]) - month_index(previous["d"])
        delta = point["v"] - previous["v"]
        slope = delta / months
        period_growth = (point["v"] / previous["v"] - 1) * 100
        monthly_growth = ((point["v"] / previous["v"]) ** (1 / months) - 1) * 100
        acceleration = None
        interval_is_proxy = bool(point.get("qualifier") or previous.get("qualifier"))
        if intervals:
            prior = intervals[-1]
            midpoint_months = (months + prior["months"]) / 2
            acceleration = (slope - prior["slope"]) / midpoint_months
        intervals.append({
            "months": months,
            "slope": slope,
            "acceleration": acceleration,
            "is_proxy": interval_is_proxy,
        })
        proxy = "≈" if interval_is_proxy else ""
        acceleration_is_proxy = interval_is_proxy or bool(intervals[-2]["is_proxy"] if len(intervals) > 1 else False)
        acceleration_prefix = "≈" if acceleration_is_proxy else ""
        acceleration_text = "—" if acceleration is None else f'{acceleration_prefix}{fmt_number(acceleration)} 億/月²'
        rows.append(
            f'<tr><td>{esc(point["d"])}<small>{esc(point["label"])}</small></td>'
            f'<td class="num"><b>{esc(display)} 億</b></td>'
            f'<td class="num">{months}</td><td class="num">{proxy}{fmt_number(delta)} 億</td>'
            f'<td class="num">{proxy}{fmt_number(slope)} 億/月</td>'
            f'<td class="num">{proxy}{period_growth:.1f}%</td>'
            f'<td class="num">{proxy}{monthly_growth:.1f}%</td>'
            f'<td class="num">{esc(acceleration_text)}</td>'
            f'<td>{source_badge(point["source_type"])} {esc(point["source"])}</td></tr>'
        )
    latest_interval = intervals[-1]
    prior_interval = intervals[-2] if len(intervals) > 1 else None
    latest_point = points[-1]
    latest_display = f'{latest_point.get("qualifier", "")}{fmt_number(latest_point["v"], 2)} 億'
    latest_acceleration = latest_interval["acceleration"]
    prior_slope_display = (
        "—"
        if prior_interval is None
        else f'{"≈" if prior_interval["is_proxy"] else ""}{fmt_number(prior_interval["slope"])} 億/月'
    )
    recent_prefix = "≈" if latest_interval["is_proxy"] else ""
    acceleration_is_proxy = latest_interval["is_proxy"] or bool(prior_interval and prior_interval["is_proxy"])
    acceleration_prefix = "≈" if acceleration_is_proxy else ""
    acceleration_display = "—" if latest_acceleration is None else f'{acceleration_prefix}{fmt_number(latest_acceleration)} 億/月²'
    metrics = (
        '<div class="metric-grid">'
        f'<div class="metric"><span>最新 run-rate</span><strong>{esc(latest_display)}</strong></div>'
        f'<div class="metric"><span>前段門檻代理</span><strong>{esc(prior_slope_display)}</strong></div>'
        f'<div class="metric"><span>近期門檻代理</span><strong>{recent_prefix}{fmt_number(latest_interval["slope"])} 億/月</strong></div>'
        f'<div class="metric"><span>二階導示意代理</span><strong>{esc(acceleration_display)}</strong></div>'
        '</div>'
    )
    return (
        f'<div class="card"><h3>{esc(momentum["title"])}</h3>{metrics}'
        f'<p class="desc">{esc(momentum["note"])}</p>'
        + table(
            ["觀測月", "ARR", "間隔月", "區間增量", "月均新增（一階導）", "期間成長", "月複合增速", "加速度代理（二階導）", "來源"],
            "".join(rows),
        )
        + f'<p class="desc calc-note">計算式：一階導＝ARR 增量÷間隔月；二階導代理＝相鄰一階導之差÷兩段間隔月數平均。'
        f'「≈」代表把報導下限門檻或約數代入的示意情境；兩個下限相減不構成真實增量的上界或下界。'
        f'最新值是「{esc(latest_display)}」下限，實際斜率與二階導無法由附件確定。'
        f'這是可能的放緩拐點，不是已確認的需求反轉。'
        f' 資料整理：{source_badge(momentum["source_type"])} {esc(momentum["source"])}</p></div>'
    )

def render_cost():
    a = D["cost"]["alphasense"]
    a_rows = "".join(
        f'<tr><td><b>{esc(r["model"])}</b></td><td>{esc(r["maker"])}</td><td>{esc(r["type"])}</td>'
        f'<td class="num">{esc(r["quality"])}</td><td>{esc(r["cost"])}</td></tr>'
        for r in a["rows"]
    )
    aa = D["cost"]["aa"]
    numeric_costs = [r.get("cost_usd") for r in aa["rows"] if r.get("cost_usd") is not None]
    numeric_scores = [r.get("ii_value") for r in aa["rows"] if r.get("ii_value") is not None]
    fable = next(
        (r["cost_usd"] for r in aa["rows"] if "Fable" in r["model"] and r.get("cost_usd") is not None),
        None,
    )
    if (
        len(numeric_costs) == len(aa["rows"])
        and len(numeric_scores) == len(aa["rows"])
        and fable
        and all("note" in r for r in aa["rows"])
    ):
        aa_rows = "".join(
            f'<tr><td><b>{esc(r["model"])}</b></td><td class="num">{fmt_number(r["ii_value"])}</td>'
            f'<td class="num">US${fmt_number(r["cost_usd"], 2)}</td>'
            f'<td class="num">{r["cost_usd"] / fable * 100:.0f}%</td><td>{esc(r["note"])}</td></tr>'
            for r in aa["rows"]
        )
        aa_table = table(["模型", "智力指數", "每任務成本", "Fable＝100", "判讀"], aa_rows)
    else:
        aa_rows = "".join(
            f'<tr><td><b>{esc(r["model"])}</b></td><td class="num">{esc(r["ii"])}</td><td>{esc(r["cost"])}</td></tr>'
            for r in aa["rows"]
        )
        aa_table = table(["模型", "智力指數", "每任務成本"], aa_rows)
    p_rows = "".join(
        f'<tr><td><b>{esc(r["model"])}</b></td><td class="num">{esc(r["input"])}</td>'
        f'<td class="num">{esc(r["output"])}</td><td>{esc(r["note"])}</td></tr>'
        for r in D["cost"]["pricing"]
    )
    insights = "".join(f"<li>{esc(t)}</li>" for t in D["cost"]["insights"])
    return (
        f'<p class="intro">{esc(D["cost"]["intro"])}</p>'
        f'<div class="card"><h3>AlphaSense 實測（金融分析 245 題）</h3><p class="desc">{esc(a["desc"])}</p>'
        + table(["模型", "廠商", "類型", "品質分數", "每題成本"], a_rows)
        + f'</div><div class="card"><h3>模型能力 vs 任務成本</h3><p class="desc">{esc(aa["desc"])} '
        + source_badge(aa.get("source_type", "third_party_benchmark"))
        + f' {esc(aa.get("source", ""))}｜快照：{esc(aa.get("as_of", ""))}</p>'
        + aa_table
        + '</div><div class="card"><h3>API 定價現況（美元／百萬 token）</h3>'
        + table(["模型", "輸入", "輸出", "備註"], p_rows)
        + f'</div><div class="card insight"><h3>關鍵洞察</h3><ul>{insights}</ul></div>'
    )

def render_monetization():
    item = D.get("revenue", {}).get("monetization")
    if not item:
        return ""
    rows = []
    for row in item["rows"]:
        premium = row["spend_share_pct"] / row["token_share_pct"]
        coding_share = "—"
        if row.get("coding_agent_spend_share_pct") is not None:
            coding_share = f'{row.get("coding_agent_qualifier", "")}{fmt_number(row["coding_agent_spend_share_pct"])}%'
        rows.append(
            f'<tr><td><b>{esc(row["company"])}</b></td>'
            f'<td class="num">{fmt_number(row["token_share_pct"])}%</td>'
            f'<td class="num">{fmt_number(row["spend_share_pct"])}%</td>'
            f'<td class="num"><b>{premium:.2f}x</b></td><td class="num">{esc(coding_share)}</td></tr>'
        )
    hero = next(
        (row for row in item["rows"] if row["company"] == "Anthropic"),
        item["rows"][0],
    )
    hero_premium = hero["spend_share_pct"] / hero["token_share_pct"]
    hero_coding = "—"
    if hero.get("coding_agent_spend_share_pct") is not None:
        hero_coding = f'{hero.get("coding_agent_qualifier", "")}{fmt_number(hero["coding_agent_spend_share_pct"])}%'
    metrics = (
        '<div class="metric-grid">'
        f'<div class="metric"><span>Token share</span><strong>{fmt_number(hero["token_share_pct"])}%</strong></div>'
        f'<div class="metric"><span>Spend share</span><strong>{fmt_number(hero["spend_share_pct"])}%</strong></div>'
        f'<div class="metric"><span>Monetization Premium</span><strong>{hero_premium:.2f}x</strong></div>'
        f'<div class="metric"><span>Coding agents 支出</span><strong>{esc(hero_coding)}</strong></div>'
        '</div>'
    )
    return (
        f'<div class="card"><h3>{esc(item["title"])}</h3>{metrics}'
        f'<p class="desc">Monetization Premium＝Spend Share÷Token Share。{esc(item["note"])}</p>'
        + table(["公司", "Token share", "Spend share", "變現溢價", "Coding agents 支出份額"], "".join(rows))
        + f'<p class="desc calc-note">樣本：{esc(item["sample"])}｜{source_badge(item["source_type"])} '
        f'{source_link(item["source"], item.get("url"))}｜{esc(item["as_of"])}</p></div>'
    )

def render_product_comparison():
    comparison = D.get("revenue", {}).get("product_comparison")
    if not comparison:
        return ""
    rows = []
    for row in comparison["rows"]:
        delta = row["arr_latest"] - row["arr_start"]
        growth = delta / row["arr_start"] * 100
        latest_week = row.get("latest_week_delta")
        if latest_week is None and len(row.get("points", [])) >= 2:
            latest_week = row["points"][-1] - row["points"][-2]
        latest_week_display = "—" if latest_week is None else f'{fmt_signed(latest_week)} 億美元'
        rows.append(
            f'<tr><td><b>{esc(row["product"])}</b><small>{esc(row["company"])}</small></td>'
            f'<td class="num">{fmt_number(row["arr_start"])} 億美元</td>'
            f'<td class="num">{fmt_number(row["arr_latest"])} 億美元</td>'
            f'<td class="num">{fmt_signed(delta)} 億美元</td><td class="num"><b>{fmt_signed(growth)}%</b></td>'
            f'<td class="num">{esc(latest_week_display)}</td></tr>'
        )
    first, second = comparison["rows"][:2]
    latest_ratio = first["arr_latest"] / second["arr_latest"]
    gap_points = comparison.get("gap_points", [])
    has_reported_gaps = len(gap_points) >= 2
    start_gap = gap_points[0] if has_reported_gaps else first["arr_start"] - second["arr_start"]
    latest_gap = gap_points[-1] if has_reported_gaps else first["arr_latest"] - second["arr_latest"]
    gap_change = None if start_gap == 0 else (latest_gap / start_gap - 1) * 100
    gap_change_display = "—" if gap_change is None else f'{gap_change:.1f}%'
    metrics = (
        '<div class="metric-grid">'
        f'<div class="metric"><span>最新規模比</span><strong>{latest_ratio:.2f}x</strong></div>'
        f'<div class="metric"><span>期初差距</span><strong>{fmt_number(start_gap)} 億</strong></div>'
        f'<div class="metric"><span>最新差距</span><strong>{fmt_number(latest_gap)} 億</strong></div>'
        f'<div class="metric"><span>差距變化</span><strong>{esc(gap_change_display)}</strong></div>'
        '</div>'
    )
    weekly_table = ""
    dates = comparison.get("dates", [])
    if dates and all(len(row.get("points", [])) == len(dates) for row in comparison["rows"][:2]):
        use_reported_gaps = len(gap_points) == len(dates)
        weekly_rows = "".join(
            f'<tr><td>{esc(date)}</td><td class="num">{fmt_number(first["points"][index])} 億</td>'
            f'<td class="num">{fmt_number(second["points"][index])} 億</td>'
            f'<td class="num">{fmt_number(gap_points[index] if use_reported_gaps else first["points"][index] - second["points"][index])} 億</td></tr>'
            for index, date in enumerate(dates)
        )
        weekly_table = '<p class="desc"><b>每週追蹤序列</b></p>' + table(
            ["週別", first["product"], second["product"], "差距"], weekly_rows
        )
    return (
        f'<div class="card"><h3>{esc(comparison["title"])}</h3>{metrics}'
        + table(["產品", comparison["start_as_of"], comparison["as_of"], "ARR 增量", "全視窗增長", "最近一週增量"], "".join(rows))
        + weekly_table
        + f'<p class="desc">{esc(comparison["note"])}</p>'
        f'<p class="desc calc-note">{source_badge(comparison["source_type"])} '
        f'{source_link(comparison["source"], comparison.get("url"))}｜單位：{esc(comparison["unit"])}</p></div>'
    )

def render_revenue():
    rows = "".join(
        f'<tr><td><b>{esc(r["company"])}</b></td><td>{esc(r["arr"])}</td><td>{esc(r["growth"])}</td>'
        f'<td>{esc(r["profit"])}</td><td>{esc(r["valuation"])}</td><td>{esc(r["mix"])}</td></tr>'
        for r in D["revenue"]["rows"]
    )
    obs = "".join(f"<li>{esc(t)}</li>" for t in D["revenue"]["observations"])
    return (
        table(["公司", "最新 ARR", "成長軌跡", "獲利能力", "估值", "營收結構"], rows)
        + render_monetization()
        + render_product_comparison()
        + f'<div class="card note"><h3>為什麼 Gemini 的 ARR 拆不出來</h3><p>{esc(D["revenue"]["gemini_note"])}</p></div>'
        + f'<div class="card insight"><h3>觀察</h3><ul>{obs}</ul></div>'
    )

def render_compute():
    cards = "".join(
        f'<div class="card"><h3>{esc(c["company"])}</h3>'
        f'<p><b>訓練：</b>{esc(c["training"])}</p>'
        f'<p><b>推論：</b>{esc(c["inference"])}</p>'
        f'<p><b>來源比重／規模：</b>{esc(c["mix"])}</p>'
        f'<p><b>自研晶片：</b>{esc(c["asic"])}</p></div>'
        for c in D["compute"]["cards"]
    )
    return cards + f'<div class="card note"><h3>中國算力研判</h3><p>{esc(D["compute"]["china_note"])}</p></div>'

def render_contracts():
    rows = "".join(
        f'<tr><td class="nowrap">{esc(r["date"])}</td><td><b>{esc(r["buyer"])}</b></td><td>{esc(r["partner"])}</td>'
        f'<td>{esc(r["desc"])}</td><td>{esc(r["size"])}</td><td>{esc(r["status"])}</td></tr>'
        for r in D["contracts"]["rows"]
    )
    return table(["公告日", "買方", "夥伴", "內容", "金額／規模", "狀態"], rows)

def render_interconnect():
    camps = "".join(
        f'<tr><td><b>{esc(r["camp"])}</b></td><td>{esc(r["leader"])}</td><td>{esc(r["scaleup"])}</td>'
        f'<td>{esc(r["scaleout"])}</td><td>{esc(r["deploy"])}</td><td>{esc(r["status"])}</td></tr>'
        for r in D["interconnect"]["camps"]
    )
    clusters = "".join(
        f'<tr><td><b>{esc(r["cluster"])}</b></td><td>{esc(r["choice"])}</td><td>{esc(r["detail"])}</td></tr>'
        for r in D["interconnect"]["cluster_choices"]
    )
    updates = "".join(f"<li>{esc(t)}</li>" for t in D["interconnect"]["updates"])
    return (
        f'<p class="intro">{esc(D["interconnect"]["intro"])}</p>'
        + '<div class="card"><h3>互連陣營對照</h3>'
        + table(["陣營", "主導者", "Scale-up（機架內）", "Scale-out／across", "代表部署", "狀態"], camps)
        + '</div><div class="card"><h3>主要叢集的網路選擇</h3>'
        + table(["叢集", "網路架構", "細節"], clusters)
        + f'</div><div class="card insight"><h3>最新動態</h3><ul>{updates}</ul></div>'
    )

def render_method():
    src = "、".join(esc(s) for s in D["method"]["sources"])
    notes = "".join(f"<li>{esc(t)}</li>" for t in D["method"]["notes"])
    references = D["method"].get("references", [])
    ref_rows = "".join(
        f'<tr><td><b>{esc(r["label"])}</b></td><td>{esc(r["publisher"])}</td>'
        f'<td>{source_badge(r["source_type"])}</td><td>{esc(r["note"])}</td>'
        f'<td>{source_link("查看", r.get("url")) if r.get("url") else "—"}</td></tr>'
        for r in references
    )
    ref_card = ""
    if ref_rows:
        ref_card = (
            '<div class="card"><h3>本期來源口徑表</h3>'
            '<p class="desc">公司披露、媒體取得的投資人資料、第三方估算、樣本與評測分層呈現；第三方資料不視為公司官方數字。</p>'
            + table(["資料", "發布／追蹤者", "層級", "口徑說明", "連結"], ref_rows)
            + '</div>'
        )
    return (
        f'<div class="card"><h3>資料來源</h3><p>{src}</p><h3>方法與免責</h3><ul>{notes}</ul></div>'
        + ref_card
    )

def render_arr_chart():
    A = D.get("arr_series")
    if not A:
        return ""
    X0, X1, Y0, Y1 = 70, 940, 26, 380
    def xp(dstr):
        y, m = map(int, dstr.split("-"))
        idx = (y - 2023) * 12 + (m - 7)  # 2023-07 -> 0 ... 2029-01 -> 66
        return X0 + idx * ((X1 - X0) / 66.0)
    LO, HI = math.log10(0.8), math.log10(3000)
    def yp(v):
        return Y1 - (math.log10(v) - LO) / (HI - LO) * (Y1 - Y0)
    P = []
    for gv, gl in [(1, "1億"), (10, "10億"), (100, "100億"), (1000, "1,000億")]:
        gy = yp(gv)
        P.append(f'<line x1="{X0}" y1="{gy:.1f}" x2="{X1}" y2="{gy:.1f}" stroke="#26314f" stroke-width="1"/>')
        P.append(f'<text x="{X0-8}" y="{gy+4:.1f}" fill="#8fa0bf" font-size="12" text-anchor="end">{gl}</text>')
    for yr in range(2024, 2029):
        gx = xp(f"{yr}-01")
        P.append(f'<line x1="{gx:.1f}" y1="{Y0}" x2="{gx:.1f}" y2="{Y1}" stroke="#1b2440" stroke-width="1"/>')
        P.append(f'<text x="{gx:.1f}" y="{Y1+18}" fill="#8fa0bf" font-size="12" text-anchor="middle">{yr}</text>')
    P.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#3b4a6e" stroke-width="1.5"/>')
    for c in A["companies"]:
        col = c["color"]
        pts = [(xp(p["d"]), yp(p["v"]), p) for p in c["points"]]
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
        P.append(f'<polyline points="{poly}" fill="none" stroke="{col}" stroke-width="2.5"/>')
        for x, y, p in pts:
            P.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.2" fill="{col}"><title>{esc(p["label"])}</title></circle>')
        lx, ly, lp = pts[-1]
        latest_display = lp.get("display") or f'{lp.get("qualifier", "")}{lp["v"]}'
        P.append(f'<text x="{lx-6:.1f}" y="{ly-12:.1f}" fill="{col}" font-size="13" font-weight="700" text-anchor="end">{esc(c["name"])} {esc(arr_currency_display(latest_display))}</text>')
        for e in c.get("estimates", []):
            ex, ey = xp(e["d"]), yp(e["v"])
            P.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" fill="#0b1020" stroke="{col}" stroke-width="2"><title>{esc(e["label"])}</title></circle>')
        ests = c.get("estimates", [])
        if ests:
            top = max(ests, key=lambda e: e["v"])
            P.append(f'<text x="{xp(top["d"])+9:.1f}" y="{yp(top["v"])+4:.1f}" fill="{col}" font-size="11.5" opacity="0.85">第三方估 ${int(top["v"])}億</text>')
        for f_ in c.get("forecasts", []):
            fx, fy = xp(f_["d"]), yp(f_["v"])
            P.append(f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{fx:.1f}" y2="{fy:.1f}" stroke="{col}" stroke-width="1.5" stroke-dasharray="6 5" opacity="0.5"/>')
            P.append(f'<path d="M {fx:.1f} {fy-6:.1f} L {fx+6:.1f} {fy:.1f} L {fx:.1f} {fy+6:.1f} L {fx-6:.1f} {fy:.1f} Z" fill="#0b1020" stroke="{col}" stroke-width="2"><title>{esc(f_["label"])}</title></path>')
            rng = f_.get("range") or str(f_["v"])
            P.append(f'<text x="{fx+10:.1f}" y="{fy+4:.1f}" fill="{col}" font-size="11.5">預測 ${esc(rng)}億</text>')
    P.append(f'<circle cx="90" cy="{Y0+10}" r="4.2" fill="#8fa0bf"/><text x="100" y="{Y0+14}" fill="#8fa0bf" font-size="12">官方／報導年化</text>')
    P.append(f'<circle cx="215" cy="{Y0+10}" r="4.5" fill="#0b1020" stroke="#8fa0bf" stroke-width="2"/><text x="225" y="{Y0+14}" fill="#8fa0bf" font-size="12">第三方估算</text>')
    P.append(f'<path d="M 320 {Y0+4} L 326 {Y0+10} L 320 {Y0+16} L 314 {Y0+10} Z" fill="#0b1020" stroke="#8fa0bf" stroke-width="2"/><text x="334" y="{Y0+14}" fill="#8fa0bf" font-size="12">前瞻預測（假設 ARR）</text>')
    return '<svg viewBox="0 0 980 408" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto">' + "".join(P) + "</svg>"

def render_arr_bars():
    A = D.get("arr_series")
    if not A or not A.get("latest_bars"):
        return ""
    rows = A["latest_bars"]
    LO, HI = math.log10(0.5), math.log10(900)
    def bw(v):
        return max(6.0, (math.log10(v) - LO) / (HI - LO) * 610)
    P = []
    y = 8
    for r in rows:
        w = bw(r["v"])
        value_display = r.get("display") or f'{r.get("qualifier", "")}{r["v"]}'
        P.append(f'<text x="142" y="{y+15}" fill="#dbe4f5" font-size="13" text-anchor="end">{esc(r["name"])}</text>')
        P.append(f'<rect x="150" y="{y}" width="{w:.1f}" height="21" rx="4" fill="{r["color"]}" opacity="0.88"><title>{esc(r["name"])}: {esc(arr_currency_display(value_display))}（{esc(r["note"])}）</title></rect>')
        P.append(f'<text x="{150+w+8:.1f}" y="{y+15}" fill="#8fa0bf" font-size="12">{esc(arr_currency_display(value_display))}｜{esc(r["note"])}</text>')
        y += 31
    return f'<svg viewBox="0 0 980 {y+6}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto">' + "".join(P) + "</svg>"

analysis = "".join(f"<p>{esc(p)}</p>" for p in D["analysis"]["paragraphs"])

CONTENT = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(D["meta"]["title"])}</title>
<style>
:root {{ --bg:#0b1020; --panel:#131a30; --panel2:#182138; --text:#dbe4f5; --muted:#8fa0bf;
  --accent:#5eead4; --accent2:#7dd3fc; --line:#26314f; --tag:#233252; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font-family:"Noto Sans TC","Microsoft JhengHei","PingFang TC",system-ui,sans-serif;
  font-size:15px; line-height:1.75; }}
a {{ color:var(--accent2); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
header {{ padding:34px 20px 10px; text-align:center; }}
header h1 {{ margin:0; font-size:30px; letter-spacing:2px;
  background:linear-gradient(90deg,var(--accent),var(--accent2)); -webkit-background-clip:text; background-clip:text; color:transparent; }}
header p {{ color:var(--muted); margin:8px auto 0; max-width:760px; }}
.updated {{ font-size:13px; color:var(--accent); margin-top:6px; }}
nav {{ position:sticky; top:0; z-index:9; background:rgba(11,16,32,.92); backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line); display:flex; flex-wrap:wrap; justify-content:center; gap:2px; padding:8px 6px; }}
nav a {{ color:var(--text); padding:6px 13px; border-radius:8px; font-size:14px; white-space:nowrap; }}
nav a:hover {{ background:var(--panel2); text-decoration:none; color:var(--accent); }}
main {{ max-width:1180px; margin:0 auto; padding:10px 18px 60px; }}
section {{ margin-top:44px; scroll-margin-top:70px; }}
section>h2 {{ font-size:22px; border-left:4px solid var(--accent); padding-left:12px; margin-bottom:14px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:18px 20px; margin:14px 0; }}
.card h3 {{ margin:0 0 10px; font-size:17px; color:var(--accent2); }}
.card.note {{ border-left:4px solid var(--accent2); }}
.card.insight {{ border-left:4px solid var(--accent); }}
.desc,.intro {{ color:var(--muted); font-size:14px; }}
.tablewrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
th {{ background:var(--panel2); color:var(--accent2); text-align:left; padding:9px 10px; white-space:nowrap; border-bottom:2px solid var(--line); }}
td {{ padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
tr:hover td {{ background:rgba(94,234,212,.045); }}
.num {{ white-space:nowrap; }} .nowrap {{ white-space:nowrap; }}
.tag {{ display:inline-block; background:var(--tag); color:var(--accent); border-radius:6px;
  padding:1px 8px; font-size:12px; margin-right:6px; }}
.source-badge {{ display:inline-block; border:1px solid #3b4a6e; border-radius:999px; padding:0 8px;
  margin:1px 5px 1px 0; color:#c4d2ea; background:#1b2440; font-size:11px; white-space:nowrap; }}
.source-badge.company-disclosure {{ color:#86efac; border-color:#166534; background:rgba(22,101,52,.18); }}
.source-badge.media-report {{ color:#7dd3fc; border-color:#075985; background:rgba(7,89,133,.18); }}
.source-badge.third-party-estimate,.source-badge.third-party-sample,.source-badge.third-party-benchmark {{
  color:#fcd34d; border-color:#854d0e; background:rgba(133,77,14,.16); }}
.source-badge.attachment-synthesis {{ color:#c4b5fd; border-color:#5b21b6; background:rgba(91,33,182,.16); }}
.metric-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(155px,1fr)); gap:10px; margin:12px 0 16px; }}
.metric {{ background:var(--panel2); border:1px solid var(--line); border-radius:10px; padding:11px 13px; }}
.metric span {{ display:block; color:var(--muted); font-size:11.5px; }}
.metric strong {{ display:block; color:var(--accent); font-size:19px; margin-top:2px; }}
.calc-note {{ border-left:3px solid var(--line); padding-left:10px; margin-top:12px; }}
.muted-cell {{ color:var(--muted); }}
td small {{ display:block; color:var(--muted); font-size:11.5px; margin-top:2px; }}
ul.log {{ padding-left:18px; }} ul.log li {{ margin:7px 0; }}
.auto-update small {{ display:block; color:var(--muted); margin:2px 0 0 2px; font-size:11.5px; }}
.analysis p {{ background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--accent);
  border-radius:12px; padding:14px 18px; }}
footer {{ text-align:center; color:var(--muted); font-size:12.5px; padding:26px 16px; border-top:1px solid var(--line); }}
@media (max-width:640px) {{ body {{ font-size:14px; }} header h1 {{ font-size:24px; }} }}
</style></head><body>
<header>
  <h1>{esc(D["meta"]["title"])}</h1>
  <p>{esc(D["meta"]["subtitle"])}</p>
  <div class="updated">最後更新：{esc(D["meta"]["updated"])}</div>
  <div class="updated">最後巡檢：{esc(D["meta"].get("last_checked", D["meta"]["updated"]))}</div>
</header>
<nav>
  <a href="#analysis">總評</a><a href="#arrchart">ARR 圖表</a><a href="#log">每日動態</a><a href="#cost">任務成本</a>
  <a href="#revenue">營收獲利</a><a href="#compute">算力架構</a><a href="#contracts">算力合約</a>
  <a href="#interconnect">互連架構</a><a href="#method">方法說明</a>
</nav>
<main>
<section id="analysis"><h2>{esc(D["analysis"]["headline"])}</h2><div class="analysis">{analysis}</div>{render_section_updates("analysis")}</section>
<section id="arrchart"><h2>ARR 走勢圖（單位：億美元，對數刻度）</h2>
<div class="card"><h3>OpenAI vs Anthropic：年化營收軌跡與前瞻預測</h3><p class="desc">{esc(D["arr_series"]["note"]) if D.get("arr_series") else ""}</p>{render_arr_chart()}</div>
<div class="card"><h3>各公司最新 ARR 一覽</h3>{render_arr_bars()}<p class="desc">{esc(D["arr_series"]["bars_note"]) if D.get("arr_series") else ""}</p></div>
{render_arr_expectations()}
{render_arr_momentum()}
{render_section_updates("arrchart")}
</section>
<section id="log"><h2>每日動態</h2>{render_daily_log()}</section>
<section id="cost"><h2>任務成本比較</h2>{render_cost()}{render_section_updates("cost")}</section>
<section id="revenue"><h2>營收與獲利能力</h2>{render_revenue()}{render_section_updates("revenue")}</section>
<section id="compute"><h2>算力架構（訓練×推論×來源比重）</h2>{render_compute()}{render_section_updates("compute")}</section>
<section id="contracts"><h2>算力與基建合約</h2>{render_contracts()}{render_section_updates("contracts")}</section>
<section id="interconnect"><h2>互連架構</h2>{render_interconnect()}{render_section_updates("interconnect")}</section>
<section id="method"><h2>方法說明</h2>{render_method()}</section>
</main>
<footer>AI 模型情報站｜每日 07:00（台北）自動更新｜本站為公開資訊彙整，非投資建議</footer>
</body></html>"""

# ---------- 加密並輸出 ----------
enc_page = encrypt(CONTENT.encode("utf-8"))
enc_data = encrypt(json.dumps(D, ensure_ascii=False).encode("utf-8"))

SHELL = """<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 模型情報站</title>
<style>
body { margin:0; background:#0b1020; color:#dbe4f5; font-family:"Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;
  display:flex; align-items:center; justify-content:center; min-height:100vh; }
.box { background:#131a30; border:1px solid #26314f; border-radius:16px; padding:38px 34px; width:min(92vw,380px); text-align:center; }
h1 { font-size:22px; margin:0 0 6px; background:linear-gradient(90deg,#5eead4,#7dd3fc);
  -webkit-background-clip:text; background-clip:text; color:transparent; }
p { color:#8fa0bf; font-size:14px; margin:0 0 22px; }
input { width:100%; padding:12px 14px; border-radius:10px; border:1px solid #26314f; background:#0b1020;
  color:#dbe4f5; font-size:16px; outline:none; }
input:focus { border-color:#5eead4; }
button { width:100%; margin-top:14px; padding:12px; border:none; border-radius:10px; font-size:16px;
  background:linear-gradient(90deg,#5eead4,#7dd3fc); color:#08101f; font-weight:700; cursor:pointer; }
button:disabled { opacity:.55; }
.err { color:#fda4af; font-size:13px; margin-top:12px; min-height:18px; }
</style></head><body>
<div class="box">
  <h1>AI 模型情報站</h1>
  <p>本站內容已加密，請輸入密碼</p>
  <input id="pw" type="password" placeholder="密碼" autofocus>
  <button id="go">解鎖</button>
  <div class="err" id="err"></div>
</div>
<script>
const PAYLOAD = __PAYLOAD__;
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
async function decrypt(pw) {
  const km = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
    { name:"PBKDF2", salt:b64(PAYLOAD.salt), iterations:PAYLOAD.iter, hash:"SHA-256" },
    km, { name:"AES-GCM", length:256 }, false, ["decrypt"]);
  const pt = await crypto.subtle.decrypt({ name:"AES-GCM", iv:b64(PAYLOAD.iv) }, key, b64(PAYLOAD.ct));
  return new TextDecoder().decode(pt);
}
async function go() {
  const pw = document.getElementById("pw").value;
  const btn = document.getElementById("go"); btn.disabled = true; btn.textContent = "解鎖中…";
  try {
    const html = await decrypt(pw);
    try { sessionStorage.setItem("aimt_pw", pw); } catch(e) {}
    document.open(); document.write(html); document.close();
  } catch(e) {
    document.getElementById("err").textContent = "密碼錯誤，請再試一次";
    btn.disabled = false; btn.textContent = "解鎖";
  }
}
document.getElementById("go").addEventListener("click", go);
document.getElementById("pw").addEventListener("keydown", e => { if (e.key === "Enter") go(); });
(async () => {
  let saved = null;
  try { saved = sessionStorage.getItem("aimt_pw"); } catch(e) {}
  if (saved) { document.getElementById("pw").value = saved; go(); }
})();
</script></body></html>"""

shell = SHELL.replace("__PAYLOAD__", json.dumps(enc_page))

def write_output_pair(outputs):
    """Write both generated files only after every payload is ready."""
    temporary = []
    try:
        for path, content in outputs:
            fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=ROOT)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            temporary.append((tmp, path))
        for tmp, path in temporary:
            os.replace(tmp, path)
    finally:
        for tmp, _ in temporary:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass

write_output_pair([
    (os.path.join(ROOT, "data.enc"), json.dumps(enc_data)),
    (os.path.join(ROOT, "index.html"), shell),
])

print("OK: index.html (%d bytes), data.enc (%d bytes)" % (
    os.path.getsize(os.path.join(ROOT, "index.html")),
    os.path.getsize(os.path.join(ROOT, "data.enc"))))
