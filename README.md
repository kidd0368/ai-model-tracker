# ai-model-tracker

AI 模型情報站：每日自動追蹤 ChatGPT、Claude 與全球大模型動向。

- `index.html` — 加密後的儀表板（AES-256-GCM，瀏覽器端 WebCrypto 解密，需密碼）
- `data.enc` — 加密的結構化資料（更新流程以 `decrypt.py` 還原）
- `build.py` — 由 `data.json` 產生並加密 `index.html` 與 `data.enc`
- `decrypt.py` — 還原 `data.json` 供每日更新編輯

更新流程（自動）：`decrypt.py` → 編輯 `data.json`（新增當日動態、改寫受影響版塊與總評、`version`+1、更新 `updated`）→ `build.py` → commit & push。

明文 `data.json` 不入庫（見 `.gitignore`）。
