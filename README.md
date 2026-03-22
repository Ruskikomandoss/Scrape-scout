# Scrape Scout

Scrape Scout is a web scraping configuration generator. Give it a URL or raw HTML and it produces a structured JSON config with CSS selectors, XPaths, confidence scores, and a ready-to-run BeautifulSoup script — no manual inspection required.

## How it works

Scout runs a six-stage pipeline:

```
HTML / URL
    │
    ▼
[1] Parser          — BeautifulSoup extracts all meaningful blocks (div, article, p, …)
    │
    ▼
[2] Classifier      — facebook/bart-large-mnli labels each block (main content / nav / ad / …)
[3] NER             — dslim/bert-base-NER counts named entities to boost signal
    │                 (boilerplate, ads, nav filtered out here)
    ▼
[4] Reasoner        — LLM searches for selectors across a fixed 35-field catalog
    │
    ▼
[5] Validator       — soup.select() confirms every selector actually matches the HTML
    │
    ▼
[6] Output          — JSON config + ready-to-run Python script
```

Stages 2–3 run locally (no API cost). Stage 4 calls your chosen LLM.

## The 35-field catalog

Instead of letting the LLM invent fields, Scout always checks for the same predefined set:

| Category | Fields |
|---|---|
| **SEO** | page_title, meta_description, meta_keywords, canonical_url, og_title, og_description, og_image, og_type, meta_robots, structured_data, hreflang, page_lang |
| **Content** | h1, h2_list, article_body, author, publish_date, modified_date, featured_image, article_category, article_tags, breadcrumbs |
| **E-commerce** | product_name, product_price, product_original_price, product_description, product_sku, product_availability, product_rating, product_review_count |
| **Structure** | primary_nav, site_logo, search_form, pagination, footer_links |

Fields present on the page get a validated selector. Fields absent get `found: false`. Every run produces the same schema, making results comparable across pages.

## Setup

```bash
pip install -r requirements.txt
```

If you plan to use JS rendering, also install the Chromium browser:
```bash
playwright install chromium
```

Copy `.env` and fill in the keys for the providers you want to use:

```
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
HUGGINGFACE_TOKEN=...   # optional — only needed for private/gated HF models
```

You only need the key for the provider you plan to use.

## Running

```bash
python main.py
```

Opens a Gradio UI at `http://127.0.0.1:7860`.

## UI tabs

| Tab | Purpose |
|---|---|
| **Input** | Paste HTML or enter a URL (auto-fetches on blur). Optional hint to focus the LLM on specific fields or categories. |
| **Output** | Full 35-field JSON config + validated Python scraper snippet. Download buttons for both. |
| **Reasoning Log** | Raw LLM response before parsing — useful for debugging. |
| **History** | All past runs stored in SQLite (`runs.db`). Load any previous result back into the Output tab. |

## Supported models

| Provider | Models |
|---|---|
| Anthropic | Claude Sonnet 4.6, Opus 4.6, Haiku 4.5 |
| OpenAI | GPT-4o, GPT-4o mini, o3-mini |
| Google | Gemini 2.0 Flash, 1.5 Pro, 1.5 Flash |
| Ollama | Any local model — enter model name and base URL in the UI |

## Output format

**JSON config** (`scraper_config.json`):
```json
{
  "source_url": "https://example.com/article",
  "generated_at": "2026-03-22T10:00:00+00:00",
  "fields": [
    {
      "field_name": "article_body",
      "found": true,
      "css_selector": "div.article-content",
      "xpath": "//div[contains(@class,'article-content')]",
      "confidence": 0.91,
      "fragility": "low",
      "fragility_reason": "semantic class name",
      "warning": null,
      "match_count": 1,
      "match_sample": "The quick brown fox…",
      "valid": true
    },
    {
      "field_name": "product_price",
      "found": false,
      "css_selector": "",
      "xpath": "",
      "confidence": 0.0,
      "fragility": "low",
      "fragility_reason": "not present on this page",
      "warning": null,
      "match_count": 0,
      "match_sample": null,
      "valid": false
    }
  ]
}
```

**Python snippet** (`scraper_snippet.py`) — only includes `valid: true` fields:
```python
import requests
from bs4 import BeautifulSoup

url = "https://example.com/article"
response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(response.text, "lxml")

results = {}
results["article_body"] = soup.select_one("div.article-content").get_text(strip=True)
results["author"] = soup.select_one("span.byline-author").get_text(strip=True)

print(results)
```

## Project structure

```
scout/
├── main.py             # Gradio UI + pipeline orchestration
├── scout/
│   ├── parser.py       # Stage 1 — BS4 block extraction
│   ├── classifier.py   # Stages 2–3 — HF classification + NER
│   ├── reasoner.py     # Stage 4 — LLM selector generation (multi-provider)
│   ├── validator.py    # Stage 5 — selector validation against source HTML
│   ├── output.py       # Stage 6 — JSON config + BS4 snippet generation
│   ├── fields.py       # 35-field extraction catalog
│   ├── fetcher.py      # URL fetching — static (requests) and JS-rendered (Playwright)
│   └── storage.py      # SQLite persistence (runs.db)
├── requirements.txt
└── .env
```

## JS rendering

For pages built with React, Vue, Angular, Next.js (CSR), or any framework that populates the DOM via JavaScript, plain HTTP fetching returns near-empty HTML. Enable **Use JS rendering** in the Input tab to use a headless Chromium browser instead.

**Prerequisite** (one-time):
```bash
playwright install chromium
```

**Wait until** controls when Playwright captures the DOM after navigation:

| Option | When to use |
|---|---|
| `networkidle` | Best for SPAs — waits until no network requests for 500 ms. Slowest but most complete. |
| `load` | `window.load` fired — most resources finished. Good middle ground. |
| `domcontentloaded` | DOM parsed, scripts may still be running. Fastest, may miss lazy-loaded content. |

## Notes

- HuggingFace models are downloaded on first run (~1.5 GB total) and cached locally
- All pipeline stages have independent error handling — a failure in one stage does not abort the run
- `runs.db` is created automatically in the project root on first run
