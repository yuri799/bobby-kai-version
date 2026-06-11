# Writing With AI — Editorial Studio (Developer Guide)

**Internal documentation.** This README explains how the project works for someone setting it up and maintaining it. It is not customer-facing copy — we will replace it before shipping.

---

## What this project is

This is a **local web app + automation scripts** for **Writing With AI** (Bobby Kania). It helps:

1. **Research** what’s trending in AI + writing (via Perplexity)
2. **Suggest article topics** from that research
3. **Write articles** in Bobby’s voice (via DeepSeek)
4. **Generate images** for articles (via OpenAI)
5. **Save drafts to Substack** automatically (via unofficial Substack library)
6. **Export** to WordPress / Markdown when needed

There is a **browser UI** for manual work and an **agent** for scheduled automation.

**Important:** The agent creates **Substack drafts only**. A human must still open Substack, review, and publish. Nothing goes live automatically.

---

## Big picture (how the pieces connect)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         YOU (browser or scheduler)                       │
└─────────────────────────────────────────────────────────────────────────┘
         │                                    │
         ▼                                    ▼
┌─────────────────┐                 ┌─────────────────┐
│   app.py        │                 │   agent.py      │
│   (Flask UI)    │                 │   (CLI agent)   │
└────────┬────────┘                 └────────┬────────┘
         │                                    │
         │         ┌──────────────────────────┘
         ▼         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        ARTICLE GENERATION                                │
│  research.py → topic_pool.json → topic_queue.json → run_generation_job  │
│       │              │                  │                    │         │
│  DeepSeek        topic ideas        work queue          DeepSeek text  │
│  research        + trend scores     (pending/done)      + OpenAI images│
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ substack_publish│  →  Draft appears in Substack (not published)
└─────────────────┘
```

### Two ways to use the system

| Mode | Best for |
|------|----------|
| **UI** (`python app.py`) | Trying topics, editing drafts, manual control |
| **Agent** (`python agent.py run`) | Daily automated research + drafting on a schedule |

Both use the same generation code under the hood.

---

## UI tabs (what each one does)

Open `http://localhost:5000` after starting the app.

| Tab | Purpose |
|-----|---------|
| **Create** | Enter a topic + direction. **Generate** writes the article. **Add to queue** saves the brief for later. |
| **Draft** | Edit the article (Markdown). Preview it. **Prepare copies** enables WordPress / HTML / Markdown copy buttons. |
| **Queue** | List of saved topics waiting to be run. **Run next** generates the top pending item and saves to Substack. |
| **Agent** | Edit all agent settings (schedule, research areas, limits). View status. **Save settings** writes `agent_config.json`. **Run now** forces a full cycle. |

---

## The agent pipeline (automated mode)

When you run `python agent.py run` (or click **Run now** in the Agent tab), this happens **if the schedule says it’s time** (or you pass `--force`):

### Step 1 — Research (`research.py`)

- For each string in `research_areas` (in `agent_config.json`), the app asks **Perplexity** (`sonar-pro`) what’s timely in that space (last N days).
- Perplexity returns web-grounded research notes (trends, tools, reader questions).

### Step 2 — Topic extraction (DeepSeek)

- DeepSeek reads the research notes and outputs **structured topic ideas** (JSON):
  - `topic` — article title
  - `brief` — editorial direction for the writer model
  - `keyword`, `subtitle`
  - `trend_score` — 1–10 (how timely + relevant)
  - `trend_reason` — why it scored that way

### Step 3 — Topic pool (`topic_pool.json`)

- New ideas are stored in **`topic_pool.json`**.
- Duplicates (same title) are skipped.
- Status starts as `available`.

### Step 4 — Pick (`agent.py pick`)

- Picks the best available topics from the pool:
  - `trend_score` ≥ `min_trend_score` (default 6)
  - Not too old (`max_pool_age_days`)
  - Not a duplicate of something recently queued/drafted
- Moves winners into **`topics_queue.json`** as `pending` jobs.
- Marks pool items as `queued`.

### Step 5 — Draft (`agent.py draft`)

- Takes `pending` queue items (up to `articles_per_day`).
- Calls **`run_generation_job`** (same as the UI):
  1. DeepSeek writes the article (Bobby voice + `author_profile.json` + `voice_library/`)
  2. OpenAI generates images (if `image_count` > 0)
  3. **python-substack** uploads images and creates a **Substack draft**
- Queue item → `done` (with Substack edit URL). Pool item → `drafted`.
- Logs go to **`agent_log.jsonl`**.

### Schedule (when things run)

Configured in `agent_config.json`:

| Setting | Meaning |
|---------|---------|
| `research_time` | Earliest time of day to run research (e.g. `06:00`) |
| `draft_time` | Earliest time to pick + draft (e.g. `07:00`) |
| `timezone` | IANA timezone (e.g. `America/New_York`) |
| `articles_per_day` | Max drafts created per calendar day |

Research runs **once per day** after `research_time`. Drafting runs after `draft_time` if under the daily limit.

`runtime` fields in the config track what already ran today (you normally don’t edit these by hand).

---

## Article generation (what the AI actually does)

When any part of the system “generates an article,” `app.py` runs this logic:

### 1. Build the prompt

Reads:

- **`author_profile.json`** — name, audience, voice notes, positioning
- **`voice_library/*.txt`** — random samples of Bobby’s real writing (if any exist)

The system prompt tells the model:

- Write in Bobby’s voice
- **Do not invent** personal stories, credentials, or experiences not in the library

### 2. Write text (DeepSeek)

- Model: `deepseek-v4-pro` (configurable via `TEXT_MODEL` in `.env`)
- Output: Markdown with an `# H1` title, `##` / `###` sections, optional `[IMAGE_1]` markers

### 3. Generate images (OpenAI, optional)

- Model: `gpt-image-2` (configurable)
- Images saved to `static/generated/`
- Markers in the article are replaced with `![alt](/static/generated/...)`

### 4. Substack draft (`substack_publish.py`)

- Extracts title from `# H1`, optional subtitle from a `>` blockquote line
- Converts local image paths so **python-substack** uploads them to Substack’s CDN
- Creates a draft via `Api.post_draft()` — **does not publish**

---

## External services & API keys

All secrets go in **`.env`** (copy from `.env.example`). Never commit `.env`.

| Variable | Service | Used for |
|----------|---------|----------|
| `PERPLEXITY_API_KEY` | [Perplexity Sonar](https://docs.perplexity.ai/) | Agent research |
| `DEEPSEEK_API_KEY` | [DeepSeek API](https://api.deepseek.com) | Topic extraction + article writing |
| `OPENAI_API_KEY` | OpenAI | Article images (`gpt-image-2`) |
| `EMAIL` + `PASSWORD` | Substack (via python-substack) | Creating drafts |
| `PUBLICATION_URL` | Substack | Which newsletter (e.g. `https://writingwithai.substack.com`) |

### Substack login

The [python-substack](https://github.com/ma2za/python-substack) library expects:

```env
EMAIL=your@email.com
PASSWORD=your_substack_password
PUBLICATION_URL=https://writingwithai.substack.com
```

**If the Substack account only uses magic-link email login** (no password):

1. Sign out of Substack → “Sign in with password” → “Set a new password”, **or**
2. Use cookie auth instead: copy the browser `Cookie` header into `COOKIES_STRING` in `.env`

Substack has **no official publish API**. This uses an unofficial client; it can break if Substack changes their backend.

---

## Project files (what lives where)

### You edit these

| File / folder | What to put there |
|---------------|-------------------|
| `.env` | API keys and Substack credentials |
| `agent_config.json` | Agent schedule, research areas, daily limits (copy from `agent_config.example.json`) |
| `author_profile.json` | Bobby’s name, audience, voice description |
| `voice_library/*.txt` | Real Bobby articles/snippets (UTF-8 text). **Critical for quality.** |

### The app creates / updates these (don’t commit)

| File | Contents |
|------|----------|
| `topics_queue.json` | Manual + agent queue of articles to write |
| `topic_pool.json` | Researched topic ideas waiting to be picked |
| `agent_log.jsonl` | One JSON line per agent event (debugging) |
| `static/generated/*.png` | Generated article images |

### Source code map

| File | Role |
|------|------|
| `app.py` | Flask server, API routes, article + image generation |
| `agent.py` | CLI for agent: `status`, `research`, `pick`, `draft`, `run` |
| `agent_config.py` | Load/save agent config, schedule logic |
| `research.py` | Perplexity research + DeepSeek topic JSON |
| `topic_pool.py` | CRUD for researched ideas |
| `topic_queue.py` | CRUD for the work queue |
| `substack_publish.py` | Substack authentication + draft creation |
| `voice_library.py` | Samples `.txt` files into prompts |
| `exporters.py` | Markdown → WordPress Gutenberg / Substack HTML |
| `automate.py` | Simple CLI: one topic or queue file → Substack draft |
| `templates/index.html` | UI structure |
| `static/app.js` | UI behavior |
| `static/style.css` | UI styling |

---

## First-time setup (step by step)

### 1. Install Python

Python **3.10+** recommended. On Windows, install from [python.org](https://www.python.org/) and check “Add to PATH.”

### 2. Clone / open the project

```powershell
cd D:\Work\APPS\bobby
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

If you see a `python-dotenv` version conflict, `requirements.txt` already pins a compatible range.

### 4. Create `.env`

```powershell
copy .env.example .env
```

Fill in every key you plan to use. Minimum for **manual UI generation**:

- `DEEPSEEK_API_KEY`
- `OPENAI_API_KEY` (if you want images)
- `EMAIL`, `PASSWORD`, `PUBLICATION_URL` (if you want Substack drafts)

Minimum for **full agent**:

- All of the above, plus `DEEPSEEK_API_KEY`

### 5. Create agent config (for automation)

```powershell
copy agent_config.example.json agent_config.json
```

Edit `research_areas`, times, and `articles_per_day`.

### 6. Add voice samples

Drop `.txt` files into `voice_library/`. Even 3–5 full articles helps a lot. Without them, the model only has `author_profile.json` voice notes.

### 7. Start the UI

```powershell
python app.py
```

Open **http://localhost:5000**

### 8. Test manually before automating

1. **Create** tab → enter a topic → **Generate**
2. Check Substack → **Drafts** — a new draft should appear
3. Read it. Edit in Substack or back in the **Draft** tab.

### 9. Test the agent

```powershell
python agent.py status
python agent.py run --force
```

`--force` ignores the time-of-day schedule and runs research + pick + draft immediately.

---

## Command reference

### Web app

```powershell
python app.py
```

Runs on port `5000` (change with `PORT` in `.env`).

### Agent

```powershell
python agent.py status      # Show pool, queue, schedule state
python agent.py research    # Perplexity → topic pool only
python agent.py pick        # Move best topics from pool → queue
python agent.py draft       # Generate queue items → Substack drafts
python agent.py run         # Full daily cycle (respects schedule)
python agent.py run --force # Run everything now
```

### One-off automation (no agent schedule)

```powershell
python automate.py --topic "Your topic" --brief "Angle and key points"
python automate.py --queue topics_queue.json
```

### Daily Windows Task Scheduler

1. Open **Task Scheduler** → Create Basic Task
2. Trigger: Daily at `draft_time` from your config
3. Action: Start a program
   - Program: `python` (or full path to `python.exe`)
   - Arguments: `agent.py run`
   - Start in: `D:\Work\APPS\bobby`

Use the same Python environment where you ran `pip install`.

---

## HTTP API (for scripts or future UI)

The Flask app exposes JSON endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/generate` | Generate article (no Substack) |
| `POST` | `/api/generate-and-push` | Generate + Substack draft |
| `GET` | `/api/queue` | List queue |
| `POST` | `/api/queue` | Add queue item |
| `POST` | `/api/queue/run-next` | Run first pending item |
| `POST` | `/api/substack/draft` | Push editor content to Substack |
| `GET` | `/api/agent/status` | Agent status |
| `POST` | `/api/agent/run` | Run agent (`{"force": true}`) |
| `GET` | `/api/agent/config` | Read agent config |
| `PUT` | `/api/agent/config` | Update agent config |

---

## Configuration reference (`agent_config.json`)

```json
{
  "enabled": true,
  "research_areas": ["topic area 1", "topic area 2"],
  "schedule": {
    "timezone": "America/New_York",
    "research_time": "06:00",
    "draft_time": "07:00",
    "articles_per_day": 1
  },
  "research": {
    "model": "sonar-pro",
    "topics_per_area": 3,
    "lookback_days": 7
  },
  "selection": {
    "auto_pick": true,
    "min_trend_score": 6,
    "max_pool_age_days": 14
  },
  "article_defaults": {
    "format": "newsletter",
    "word_count": 1200,
    "image_count": 2,
    "auto_substack_draft": false,
    "audience": "everyone"
  }
}
```

| Field | What it does |
|-------|----------------|
| `enabled` | `false` stops `agent.py run` (not `--force`) |
| `research_areas` | List of strings Perplexity researches each day |
| `topics_per_area` | How many article ideas to extract per area |
| `min_trend_score` | Pool items below this score are never auto-picked |
| `auto_pick` | If `false`, research fills pool but nothing moves to queue automatically |
| `auto_substack_draft` | If `false`, agent generates articles but doesn’t push to Substack |

---

## Data flow examples

### Example A — Manual “one button” article

1. User fills **Create** form
2. `POST /api/generate-and-push`
3. DeepSeek writes article → OpenAI images → Substack draft
4. User sees draft in **Draft** tab and in Substack

### Example B — Agent daily run

1. 6:00 AM — `agent.py run` researches 3 areas × 3 topics = up to 9 pool items
2. 7:00 AM — `agent.py run` picks top scored topic → queue → generates → Substack draft
3. Bobby opens Substack, edits, publishes

### Example C — Queue batch

1. User adds 5 briefs via **Add to queue**
2. Each day, **Run next** or agent drafts one (`articles_per_day: 1`)
3. Queue items move `pending` → `done`

---

## Quality controls (avoiding generic AI content)

The system does **not** auto-guarantee quality. These levers matter:

1. **`voice_library/`** — The single biggest improvement. Use Bobby’s real posts.
2. **Specific briefs** — “How to outline a newsletter in 15 minutes” beats “AI writing tips.”
3. **Agent `research_areas`** — Narrow beats broad.
4. **`min_trend_score`** — Raise to 7–8 for fewer but sharper picks.
5. **Human review** — Always read Substack drafts before publishing.
6. **No invented stories** — Built into the prompt; still verify facts and tool claims.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|--------------|-----|
| `DEEPSEEK_API_KEY is not configured` | Missing `.env` key | Add key, restart `app.py` |

| `Substack auth is not configured` | No EMAIL/PASSWORD or cookies | Set credentials per section above |
| Substack login fails | Magic-link-only account | Set a password or use `COOKIES_STRING` |
| Empty / generic articles | No voice library files | Add `.txt` samples to `voice_library/` |
| Agent “Research not due yet” | Before `research_time` or already ran today | Use `python agent.py run --force` |
| Agent “Daily article limit reached” | `drafts_created_today` ≥ `articles_per_day` | Wait until tomorrow or raise limit |
| Images missing in Substack | Image upload failed | Check `OPENAI_API_KEY`; see `agent_log.jsonl` |
| `pip` dependency conflict | Old pinned `python-dotenv` | Use `python-dotenv>=1.2.1,<2.0.0` from `requirements.txt` |

Check **`agent_log.jsonl`** for a line-by-line trace of agent steps and error messages.

---

## Security notes

- **`.env`** holds API keys and Substack password — never commit or share it.
- **`COOKIES_STRING`** is equivalent to being logged into Substack — treat like a password.
- The app binds to localhost by default; don’t expose `app.py` to the public internet without adding proper auth.
- Review all AI-generated claims before publishing (tools, pricing, features change often).

---

## Production deployment (optional)

`Procfile` includes:

```
web: gunicorn app:app --timeout 600
```

Generation can take several minutes (text + multiple images). The 600s timeout is intentional.

The **agent** (`agent.py run`) is meant for cron / Task Scheduler, not inside the web worker.

---

## Glossary

| Term | Meaning |
|------|---------|
| **Topic pool** | Ideas from research, not yet queued for writing |
| **Queue** | Topics approved for generation (`topics_queue.json`) |
| **Brief** | Editorial direction passed to the writer model |
| **Draft** | Substack unpublished post (what we create) |
| **Agent** | Scheduled research + pick + generate pipeline |
| **Voice library** | Folder of Bobby’s writing used to match tone |

---

## Related links

- Writing With AI site: https://writingwithai.com/
- Substack: https://writingwithai.substack.com/
- python-substack: https://github.com/ma2za/python-substack

- DeepSeek API: https://api-docs.deepseek.com/

---

*This document describes the system as of the internal dev build. Replace with public-facing docs before launch.*

