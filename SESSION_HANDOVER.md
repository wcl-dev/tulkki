# tulkki — Session 接手文件

**最後更新：** 2026-04-09
**目的：** 跨裝置接手用。把這份文件跟整個 `tulkki/` 資料夾一起同步到另一台機器，新機器上的 Claude Code 讀這份就能立刻接著做，不用重新解釋。

---

## TL;DR（一段話）

tulkki v0.1 已經能跑、11 個單元測試全過、已經用 5 個真實網頁試用並修了 3 個真實 bug。今天的對話最後停在「準備發第一篇社群貼文用 Anthropic Economic Index 當釣魚案例」— 三版貼文草稿都寫好了（A 短版 / B 串文版 / C LinkedIn 長版），但**還沒選哪一版、也還沒決定是否要先把專案 push 到 GitHub**。下次接手時，第一個要問的事就是：**「貼文發了沒？如果還沒，要選哪版？要不要先發 GitHub？」**

---

## 一、目前狀態

### 工具能做什麼

`tulkki check URL` 會去抓一個網頁兩次：一次用模擬 AI 爬蟲的方式（不跑 JavaScript），一次用真實瀏覽器（跑完 JavaScript）。然後比較兩邊看到的內容，給一個可見性分數、列出 AI 看不到的章節標題、把兩個版本各存成一個 markdown 檔。

### 已經實作的指令

```sh
tulkki check URL                          # 預設：報告 + 兩份 markdown 存到 ./tulkki-out/
tulkki check URL --json                   # 機器讀的格式
tulkki check URL --quiet                  # 只印一個分數
tulkki check URL --quiet --fail-below 80  # 自動化檢查用，分數低於 80 就退出 1
tulkki check URL --no-render              # 跳過 JavaScript 那次
tulkki check URL --no-save                # 不存檔
```

### 測試狀態

`uv run pytest tests/` → **11 個測試全過**

涵蓋：標題計分、字數計分、重複標題不該扣分、字數覆蓋上限、空字數邊界、純字數 fallback、Anthropic-style 結構盲區、Markdown heading 解析、code block 內的 # 不算標題、word count strip 語法。

### 預設後端與技術棧

- **AI 視角抓取**：`httpx` + 自訂 User-Agent
- **真人視角抓取**：`playwright` 的 chromium，等 `domcontentloaded` + 2.5 秒落地
- **內容抽取**：`trafilatura`（輸出 markdown）
- **CLI 框架**：`typer`
- **報告渲染**：`rich`

### 還沒實作但介面已備好的進階後端

四個 optional dependency 的 backend 留了 import 點但沒寫實作：`hrequests`、`patchright`、`crawl4ai`、`firecrawl`。每個約 30 行就能補完。

---

## 二、今天親自試用的 5 個真實網頁

| URL | 分數 | 學到什麼 |
|---|---|---|
| `https://news.ycombinator.com/` | 78.7% | JavaScript 算的 timestamps 是真實的 visibility gap |
| `https://en.wikipedia.org/wiki/Web_scraping` | 100% | 維基百科是 server-rendered 老學校做法，AI 全看得到 |
| `https://react.dev/` | 100% | Next.js SSG 預先 build，即使是現代框架也對 AI 友善 |
| `https://docs.anthropic.com/en/docs/intro` | 70% | 早上挑的 hero case：AI 看到字、丟掉 5 個 h1/h2 結構 |
| `https://www.bbc.com/` | — | **首頁挖出 networkidle 卡死 bug**（已修）。也證實 trafilatura 不適合首頁/列表頁，內容只剩 40 字 |
| `https://www.bbc.com/news/articles/c1krpjr91v2o` | 100% | 證明工具在文章頁完全正常 |
| `https://openai.com/business/guides-and-resources/how-openai-uses-codex/` | — | **HTTP 403，挖出 Cloudflare 擋 bot 的問題**（已修：加 HTTP 狀態警告）。也挖出**重複標題扣分 bug**（已修：原本 82 分） |
| `https://openai.com/zh-Hant/index/how-we-monitor-internal-coding-agents-misalignment/` | — | 同樣 HTTP 403 被擋 |
| **`https://www.anthropic.com/economic-index`** | **5.4%** | **最強 hero case，已第二次重跑驗證可重現**。數字：53 字 vs 689 字、0 vs 4 標題、連 H1 都看不到。HTTP 200 真實回應，是真正的 SPA 殼 |

---

## 三、今天修掉的 3 個真實 bug

### Bug 1：networkidle 等待策略對廣告/追蹤多的網站會卡死

- **症狀**：BBC 首頁讓 Playwright 等了 30 秒 timeout，因為 BBC 的廣告/分析請求永遠跑不完
- **修法**：[src/tulkki/backends/playwright_render.py](src/tulkki/backends/playwright_render.py) 的 `wait_until` 從 `networkidle` 改成 `domcontentloaded`，再加 2.5 秒固定等待讓 JavaScript 落地。也用 try/except 包住 goto，如果 timeout 就還是嘗試取 DOM
- **狀態**：已修並重跑驗證

### Bug 2：重複標題會被人為扣分

- **症狀**：OpenAI Codex 頁有 1 個 h1 + 4 個重複的 h3「Anecdotes from our teams」。我的 `_heading_coverage` 算法用「去重後符合的標題數」（2）除以「沒去重的清單長度」（5），結果該 100 分變 82 分
- **修法**：[src/tulkki/diff.py](src/tulkki/diff.py) 的 `_heading_coverage` 改成兩邊都用去重後的 set 算（`matched / len(human_unique)`）
- **回歸測試**：[tests/test_diff.py](tests/test_diff.py) 的 `test_repeated_headings_do_not_penalise_score` 防止以後再壞掉
- **狀態**：已修並 11/11 測試通過

### Bug 3：HTTP 失敗會傻傻拿錯誤頁算分數

- **症狀**：OpenAI 兩頁都被 Cloudflare 擋（HTTP 403），返回 13.8 KB 的擋頁。tulkki 沒檢查狀態碼，直接拿擋頁去算字數，給出毫無意義的分數但沒任何警告
- **修法**：
  - [src/tulkki/types.py](src/tulkki/types.py) 的 `VisibilityReport` 加 `raw_status` / `render_status` 欄位
  - [src/tulkki/diff.py](src/tulkki/diff.py) 的 `compare()` 把狀態碼從 FetchResult 帶進 VisibilityReport
  - [src/tulkki/report.py](src/tulkki/report.py) 加 `_status_warning()` 函式，遇到 4xx/5xx 會在報告最上面跳紅字警告
  - JSON 輸出也包含 `status` 和 `warning` 欄位
- **狀態**：已修並重跑驗證

---

## 四、tulkki 的已知限制（要寫進 README 但還沒寫）

1. **不適合首頁/列表頁** — trafilatura 找不到「主體內容」就會回傳幾乎空的結果。例如 BBC 首頁只抽到 40 字。tulkki 適合**有主體內容的單一頁面**：文章、產品說明、單品介紹、Wikipedia 條目等
2. **預設 User-Agent 會被主流大站擋** — OpenAI 等網站用 Cloudflare 擋未知 bot。tulkki 預設送的「tulkki/0.1 AI-visibility-diagnostic」會被 403。GPTBot、ClaudeBot 等主流爬蟲在 Cloudflare 通常被列白名單，所以它們不會被擋，但 tulkki 模擬的「未知爬蟲」會。**未來該做的功能**：加 `--user-agent` 或 `--as-bot gptbot` 讓使用者切換要模擬的 bot
3. **AI 視角和真人視角的內容差異有時候是 trafilatura 抽取行為差異造成的，不是真實的 visibility gap** — 例如 HN 的 78.7% 中有一部分是兩次抽取的差異，不全是 JavaScript 造成的

---

## 五、目前在做的事：第一篇社群貼文

### 為什麼選這個策略

從早上列的四個方向（發 GitHub、補後端、寫 CI 範例、暫時不動）裡選了第 4 個的變體：用 Anthropic Economic Index 當釣魚案例先發 Twitter / LinkedIn 貼文，**在發 GitHub 之前先測試這個 framing 在社群有沒有共鳴**。理由：今天的真實試用挖出來的 bug 證明工具還沒完全穩定到該大發，但 Anthropic 的諷刺性夠強，可以當社群測水溫的便宜驗證。

### 核心釣魚標題

> **「A page about AI, hidden from AI.」**

### 核心數據（已二次驗證可重現）

- AI 視角：53 字、0 個標題
- 真人視角：689 字、4 個標題
- 可見性分數：5.4%
- 連 H1 大標題「Anthropic Economic Index」都看不到
- HTTP 200，不是被擋，是真實的 SPA 殼
- Raw 2.65 MB → Rendered DOM 14 MB（5 倍膨脹）

### 三版貼文草稿（接著就可以複製貼出去用的）

#### 版本 A：Twitter / X 短版

```
Tested anthropic.com/economic-index with a CLI tool I built that
diffs what AI crawlers see vs what humans see.

AI sees 53 words. Humans see 689.
Visibility score: 5.4%.

The page about how AI affects the economy is 94.6% invisible to AI.

A page about AI, hidden from AI.
```

#### 版本 B：Twitter 串文版（兩條）

第一條：
```
Most AI crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended)
don't run JavaScript.

So I built a CLI that fetches a URL twice — once like an AI crawler,
once like a real browser — and shows you the gap.

First serious test: anthropic.com/economic-index
```

第二條：
```
Results:
  AI crawler view:  53 words, 0 headings
  Human view:       689 words, 4 headings
  Visibility:       5.4%

Even the H1 title "Anthropic Economic Index" is invisible to AI.

Anthropic's own page about how AI affects the economy is 95% hidden
from AI.
```

#### 版本 C：LinkedIn 長版

```
Most LLM crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended)
don't execute JavaScript. If your content is rendered client-side, it
is invisible to them.

I spent yesterday building a small CLI tool that fetches any URL twice
— once with no JavaScript (the AI view) and once with full JavaScript
(the human view) — then diffs them. It gives you a visibility score, a
list of headings the AI cannot see, and two side-by-side Markdown files.

The first thing I tested seriously was anthropic.com/economic-index —
Anthropic's own landing page about how AI is reshaping the economy.

  AI crawler view:  53 words, 0 headings
  Human view:       689 words, 4 headings
  Visibility score: 5.4%

Even the H1 title "Anthropic Economic Index" does not appear in the
raw HTML. A user with a browser sees a complete page. An AI crawler
scraping the response sees an empty shell.

A few things to note:

1. This is not a bug in my tool. Anthropic's page returns HTTP 200
   with a 2.65 MB body. The body just contains the JavaScript bundle
   that builds the page client-side. After hydration the DOM grows
   to over 14 MB.

2. This is not unique to Anthropic. It is the default behaviour of
   most marketing pages built with React, Next.js, Vue, etc. Almost
   every tech company's homepage has the same problem to some degree.

3. The irony is what makes this case worth posting. The page is
   about AI. Made by a company that makes AI. Hidden from AI.

The tool is called tulkki (Finnish for "interpreter"). Going up on
GitHub later this week. If you'd like early access or want me to
test your own site, drop a comment.
```

### 發文前的待決事項

1. **選哪一版**？A、B、C，或要混搭調整
2. **要不要先發 GitHub**？兩個選項：
   - **甲**：先發貼文，文裡寫「coming to GitHub this week」或「DM for early access」
   - **乙**：先花 30 分鐘把專案 push 到 GitHub（README 已備齊），有了真正的網址再發貼文（**建議這個**）
3. **要不要先禮貌通知 Anthropic**？不是必須做的，但是個好習慣。可以在發文前一兩個小時，在 Anthropic 官方 Twitter 或 contact 管道丟一句「我用一個工具發現你們的 /economic-index 頁對 AI crawler 95% 不可見，數據在這，準備發文，給你們先看一下」。給他們機會：先修、不在乎或反過來想 collab。**不做也沒關係**

---

## 六、檔案地圖（主要的東西放哪裡）

```
c:/Users/Cordura87/tulkki/
├── pyproject.toml             # 依賴清單、optional-extras、CLI entry point
├── README.md                  # 給未來使用者看的（已經寫好定位 + 比較表）
├── LICENSE                    # MIT
├── SESSION_HANDOVER.md        # 你正在讀的這份
├── src/tulkki/
│   ├── cli.py                 # typer CLI 入口
│   ├── types.py               # FetchResult、ExtractedDoc、VisibilityReport、Heading
│   ├── protocols.py           # Fetcher、Extractor 介面
│   ├── extractor.py           # TrafilaturaExtractor
│   ├── diff.py                # _visibility_score、_heading_coverage、compare
│   ├── report.py              # render_terminal、render_json、_status_warning
│   └── backends/
│       ├── __init__.py        # get_raw_fetcher / get_rendering_fetcher
│       ├── httpx_raw.py       # 預設 raw 後端
│       └── playwright_render.py # 預設 render 後端
└── tests/
    ├── test_diff.py           # 7 個測試
    └── test_extractor.py      # 4 個測試
```

完整的計畫文件在這台機器的 `C:\Users\Cordura87\.claude\plans\enumerated-dreaming-quasar.md`，**但那個是本地的不會跟著專案跑**。如果你要在新機器看完整的設計脈絡，可以把 plan 也複製進專案資料夾。

---

## 七、在新機器上接手的步驟

```sh
# 1. 同步整個 tulkki/ 資料夾到新機器（git push、OneDrive、Dropbox 都行）

# 2. 在新機器的 tulkki/ 資料夾打開終端機

# 3. 重新安裝依賴（uv 會根據 uv.lock 裝跟原機器一模一樣的版本）
uv sync

# 4. 安裝 Playwright 的 chromium 瀏覽器（這個約 108 MB，每台機器都要裝一次）
uv run playwright install chromium

# 5. 驗證工具還能跑（這也是 hero case，跑完應該看到 5.4% 的分數）
uv run tulkki check "https://www.anthropic.com/economic-index" --no-save

# 6. 跑測試確認沒東西壞掉（應該看到 11 passed）
uv run pytest tests/

# 7. 開新的 Claude Code 對話，跟它說「讀 SESSION_HANDOVER.md」
```

---

## 八、給下次接手的 Claude 的指令

如果你（Claude）正在新機器上讀這份，使用者剛開新對話：

1. **先問**：「上次的貼文發了沒？如果還沒，是哪一版？要不要先發 GitHub？」
2. **不要主動寫程式碼** — 上次的工具狀態是穩定的，今天該做的事是社群推廣相關，不是技術修補
3. **如果使用者要發 GitHub**：幫他建立 git commit、寫 commit message（用中文）、push 到新建的 GitHub repo。README 已經備齊不用改
4. **如果使用者要修改貼文草稿**：三版（A、B、C）在第五節，直接編輯不用重畫
5. **語言**：使用者偏好白話正體中文，**不要堆技術術語**。寫文案、解釋設計、列下一步時，看到縮寫或框架名先停一下，想想「能不能用日常描述代替」。詳細規則在這台機器的 `C:\Users\Cordura87\.claude\projects\c--Users-Cordura87-tulkki\memory\feedback_avoid_jargon_abbreviations.md`，但那個本地的，新機器拿不到，所以就記住：**不堆術語、用具體動作和日常比喻、不加表情符號**
6. **未完成但留待之後的事項**（按優先序）：
   - 補上四個進階後端的實作（hrequests、patchright、crawl4ai、firecrawl）
   - 把今天的限制和 hero case 寫進 README
   - 寫 GitHub Actions 範例設定檔
   - 加 `--user-agent` 或 `--as-bot gptbot` 旗標讓使用者模擬不同 AI 爬蟲
