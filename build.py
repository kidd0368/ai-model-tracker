#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 模型情報站 - 靜態網站產生器 + AES-256-GCM 加密
用法: SITE_PASSWORD='...' python3 build.py
輸出: index.html (加密殼頁) + data.enc (加密資料備份)
"""
import json, os, sys, base64, html
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

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

def table(headers, rows_html):
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    return f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead><tbody>{rows_html}</tbody></table></div>'

def render_cost():
    a = D["cost"]["alphasense"]
    a_rows = "".join(
        f'<tr><td><b>{esc(r["model"])}</b></td><td>{esc(r["maker"])}</td><td>{esc(r["type"])}</td>'
        f'<td class="num">{esc(r["quality"])}</td><td>{esc(r["cost"])}</td></tr>'
        for r in a["rows"]
    )
    aa = D["cost"]["aa"]
    aa_rows = "".join(
        f'<tr><td><b>{esc(r["model"])}</b></td><td class="num">{esc(r["ii"])}</td><td>{esc(r["cost"])}</td></tr>'
        for r in aa["rows"]
    )
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
        + f'</div><div class="card"><h3>Artificial Analysis 每任務成本</h3><p class="desc">{esc(aa["desc"])}</p>'
        + table(["模型", "智力指數", "每任務成本"], aa_rows)
        + '</div><div class="card"><h3>API 定價現況（美元／百萬 token）</h3>'
        + table(["模型", "輸入", "輸出", "備註"], p_rows)
        + f'</div><div class="card insight"><h3>關鍵洞察</h3><ul>{insights}</ul></div>'
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
    return f'<div class="card"><h3>資料來源</h3><p>{src}</p><h3>方法與免責</h3><ul>{notes}</ul></div>'

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
ul.log {{ padding-left:18px; }} ul.log li {{ margin:7px 0; }}
.analysis p {{ background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--accent);
  border-radius:12px; padding:14px 18px; }}
footer {{ text-align:center; color:var(--muted); font-size:12.5px; padding:26px 16px; border-top:1px solid var(--line); }}
@media (max-width:640px) {{ body {{ font-size:14px; }} header h1 {{ font-size:24px; }} }}
</style></head><body>
<header>
  <h1>{esc(D["meta"]["title"])}</h1>
  <p>{esc(D["meta"]["subtitle"])}</p>
  <div class="updated">最後更新：{esc(D["meta"]["updated"])}</div>
</header>
<nav>
  <a href="#analysis">總評</a><a href="#log">每日動態</a><a href="#cost">任務成本</a>
  <a href="#revenue">營收獲利</a><a href="#compute">算力架構</a><a href="#contracts">算力合約</a>
  <a href="#interconnect">互連架構</a><a href="#method">方法說明</a>
</nav>
<main>
<section id="analysis"><h2>{esc(D["analysis"]["headline"])}</h2><div class="analysis">{analysis}</div></section>
<section id="log"><h2>每日動態</h2>{render_daily_log()}</section>
<section id="cost"><h2>任務成本比較</h2>{render_cost()}</section>
<section id="revenue"><h2>營收與獲利能力</h2>{render_revenue()}</section>
<section id="compute"><h2>算力架構（訓練×推論×來源比重）</h2>{render_compute()}</section>
<section id="contracts"><h2>算力與基建合約</h2>{render_contracts()}</section>
<section id="interconnect"><h2>互連架構</h2>{render_interconnect()}</section>
<section id="method"><h2>方法說明</h2>{render_method()}</section>
</main>
<footer>AI 模型情報站｜每日 07:00（台北）自動更新｜本站為公開資訊彙整，非投資建議</footer>
</body></html>"""

# ---------- 加密並輸出 ----------
enc_page = encrypt(CONTENT.encode("utf-8"))
enc_data = encrypt(json.dumps(D, ensure_ascii=False).encode("utf-8"))

with open(os.path.join(ROOT, "data.enc"), "w", encoding="utf-8") as f:
    json.dump(enc_data, f)

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
with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
    f.write(shell)

print("OK: index.html (%d bytes), data.enc (%d bytes)" % (
    os.path.getsize(os.path.join(ROOT, "index.html")),
    os.path.getsize(os.path.join(ROOT, "data.enc"))))
