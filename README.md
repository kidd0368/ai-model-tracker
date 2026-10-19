# ai-model-tracker

加密的 AI 模型與產業情報站。網站保留原本的 `data.json → build.py → index.html / data.enc` 設計，並由 GitHub Actions 每天蒐集第一方來源、更新資料、重新加密、提交及部署 GitHub Pages。

## 每日流程

`.github/workflows/daily-update.yml` 的目標排程是每天 **07:15 Asia/Taipei**：

1. 以 Actions Secret `SITE_PASSWORD` 解密現有 `data.enc`。
2. 驗證完整資料 schema；解密或驗證失敗便停止。
3. 讀取 `sources.json` 中的官方 RSS、Atom 與 sitemap，重掃最近 14 天並依 URL／標題去重。
4. 預設以不需要外部 AI 金鑰的確定性規則篩選、分類及產生摘要；若完整設定選用的 OpenAI-compatible enrichment endpoint，才會交由該服務強化內容，服務不可用時仍自動退回確定性摘要。
5. 新事件加入 `daily_log`，並以含來源連結的 `section_updates` 顯示在確實受影響的總評、成本、營收、算力、合約或互連區塊。既有表格、歷史與未知欄位不會被重建或刪除。
6. 更新成功後執行 schema 驗證、`build.py`、雙密文 round-trip 驗證。
7. 只允許 stage `data.enc` 與 `index.html`，再由 `github-actions[bot]` commit/push，並記錄成功推送的精確 commit SHA。
8. 部署鎖定該次已驗證的 commit（一般 push／`deploy-only` 則鎖定觸發時的 SHA），只把全新暫存目錄中的 `index.html` 部署到 Pages；明文 `data.json` 不會進入 commit 或 Pages artifact。

GitHub 排程可能因平台負載稍微延遲，07:15 是目標觸發時間，不是秒級 SLA。排程只會從 default branch 的最新版 workflow 執行。

## 必要設定

### 1. Actions Secret（必填）

在 **Settings → Secrets and variables → Actions → New repository secret** 建立：

| 名稱 | 必要性 | 說明 |
|---|---:|---|
| `SITE_PASSWORD` | 必填 | 必須是目前 `data.enc` 的精確原始密碼。錯一個字元就會 fail closed，且不修改網站。 |

Secret 只能新增／覆寫，GitHub 不會顯示既有值。本專案不需要 PAT；workflow 以 job-level `contents: write` 更新 repo。

若要更換網站密碼，必須先用舊密碼成功解密，再用新密碼重建 `data.enc` 與 `index.html`，驗證後才同步更新 `SITE_PASSWORD`。不可只改 Secret，否則下一輪無法解密。

### 2. AI enrichment（完全選填）

預設的確定性流程不需要任何外部 AI 金鑰。若希望使用 OpenAI-compatible `chat/completions` 服務強化事件篩選與繁體中文摘要，必須同時建立以下三項設定；少任何一項都不會呼叫外部服務，而會安全退回確定性流程：

| 名稱 | 類型 | 說明 |
|---|---|---|
| `AI_ENRICHMENT_TOKEN` | Actions Secret | 選用服務的 Bearer token。 |
| `AI_ENRICHMENT_ENDPOINT` | Actions Variable | 相容 API 的 base endpoint；程式會呼叫其 `/chat/completions`。 |
| `AI_ENRICHMENT_MODEL` | Actions Variable | 該服務所接受的模型 ID。 |

`AI_ENRICHMENT_TOKEN` 只注入兩個執行 `update.py` 的 step；不會提供給 checkout、安裝、解密、build、commit 或部署步驟，也不會收到 `SITE_PASSWORD`。

[GitHub Models 已在 2026-07-30 完全退役](https://docs.github.com/en/github-models)，原本的推論端點及 `models: read` 權限不再適合作為長期自動化依賴，因此本專案不再使用 `GITHUB_TOKEN` 呼叫 GitHub Models，也不提供其舊設定。供應商中立的選填設定可替換服務而不改 workflow；未設定時，每日更新仍可完整運作。

### 3. GitHub Pages（必填一次）

在 **Settings → Pages → Build and deployment → Source** 選擇 **GitHub Actions**。

不能繼續只依賴舊式 `Deploy from a branch`：GitHub 官方規則是，workflow 用內建 `GITHUB_TOKEN` push 的 commit 不會再觸發 branch-source Pages build。因此本專案在同一 workflow 內直接執行 `upload-pages-artifact` 與 `deploy-pages`。

### 4. 首次驗證

在 **Actions → Daily AI tracker update and Pages deploy → Run workflow** 依序執行：

先確認 **Run workflow** 的分支選的是 `main`；所有更新與部署工作在其他分支都會直接跳過，避免把非預期版本寫回正式站。

1. `dry-run`：驗證密碼、schema 與來源，不改 repo、不部署。
2. `update`：正式更新、加密、commit/push 並部署。
3. `deploy-only`：只重新發布目前的 `index.html`，不需要解密；適合 Pages 初次切換或純部署重試。

## 長期資料來源

目前核心來源均可由 GitHub-hosted runner 無登入取得，包含：

- OpenAI News
- Anthropic News sitemap（Anthropic 沒有官方 RSS）
- Google AI、Google DeepMind、Google Research、Vertex AI release notes
- Mistral AI News
- NVIDIA Generative AI
- Hugging Face Blog
- Microsoft Source AI
- Meta Engineering AI Research、Meta Llama GitHub Releases
- AWS Machine Learning Blog

來源必須達到 `sources.json` 設定的健康門檻才允許寫入。單一來源失敗只會記錄警告；健康來源不足則整輪停止，不會清空或重建既有資料。Feed 內容一律視為不可信輸入，下載大小、URL scheme、模型輸出路徑與欄位都有限制。

### 深度研究資料與來源分級

結構化研究欄位另外保留 `source_type`，前端以不同標籤呈現，避免把不同可信度與定義的數字混在一起：

- `company_disclosure`：公司新聞稿或直接披露。
- `media_report`：媒體取得的投資人資料或知情人士口徑，不等於公司公告。
- `third_party_estimate`：替代數據、追蹤或市場預期。
- `third_party_sample`：單一平台／gateway 樣本，不外推為全球市佔。
- `third_party_benchmark`：獨立評測與任務成本。
- `attachment_synthesis`：研究附件的跨來源整理。

Anthropic 專題資料位於 `arr_series.expectation_comparison`、`arr_series.momentum`、`revenue.monetization` 與 `revenue.product_comparison`。其中 ARR 動能由觀測點即時計算區間增量、月均新增與二階導代理；若原始值是約數或下限，前端會明確標記為「門檻值代入的示意代理」。兩個下限相減不構成真實增量的上界或下界，實際斜率與二階導仍不可確定。

### 金十數據 MCP 的狀態

2026-08-15 的「接入金十數據即時快訊」commit 只替換了 `data.enc` 與 `index.html`，repo 中從未留下 MCP client、API 設定、資料擷取器或 schedule，因此那是一次工作階段中的人工資料更新，不是可重跑的整合。

金十 MCP 屬於 ChatGPT／Codex 工作階段能力，GitHub Actions runner 不會繼承該連線。每日正式流程因此不依賴金十，也不逆向未公開端點；金十仍可在人工研究工作階段作為輔助發現來源，但任何要進站的資料都必須保留可公開驗證的來源 URL。

## 安全與失敗行為

- AES-256-GCM、PBKDF2-HMAC-SHA256、300,000 iterations、隨機 salt／IV 的既有格式不變。
- `index.html` 的頁面密文與 `data.enc` 的結構化資料密文必須由同一份 `data.json`、同一密碼成對產生。
- `decrypt.py`、`update.py` 與 `build.py` 採驗證後寫入；錯誤密碼、無效 schema 或來源 quorum 失敗時不提交。
- `verify_build.py` 會同時解密 `data.enc` 與 `index.html` 內嵌 payload，確認兩者與明文資料一致。
- `data.json` 由 `.gitignore` 排除；workflow 還會拒絕任何追蹤它的 commit，並在最後刪除 runner 上的明文。
- Pages artifact 從 runner 的全新暫存目錄建立，並以 allowlist 驗證只含 `index.html`，不會上傳 repository root。
- Pages checkout 使用已驗證的精確 commit SHA，不會在部署途中重新讀取可能已變動的 `main`。
- 財務數字、ARR、價格與合約表不會只憑一般摘要自動覆寫；這些既有結構化欄位保留，新的官方事件先以來源連結顯示在相應區塊。
- push 發生 non-fast-forward、build 驗證失敗或 staged-file allowlist 不符時停止，永不 force push。

## 本機維護

PowerShell 範例：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:SITE_PASSWORD = "<目前網站密碼>"

.\.venv\Scripts\python decrypt.py
.\.venv\Scripts\python update.py --dry-run
.\.venv\Scripts\python update.py
.\.venv\Scripts\python build.py
.\.venv\Scripts\python verify_build.py
.\.venv\Scripts\python -m unittest discover -s tests -v

Remove-Item Env:SITE_PASSWORD
```

主要檔案：

- `sources.json`：官方來源、健康門檻、回看期間與優先級。
- `update.py`：來源擷取、正規化、去重、選用的相容 AI enrichment／確定性分類及 additive update。
- `validate_data.py`：既有 schema 與新增自動更新欄位的 fail-closed 驗證。
- `decrypt.py`：`data.enc` → ignored `data.json`。
- `build.py`：`data.json` → 加密的 `index.html` 與 `data.enc`。
- `verify_build.py`：成對密文與明文 round-trip 驗證。
- `.github/workflows/daily-update.yml`：測試、每日更新、commit/push 與 Pages deployment。
