# 🦞 CangreDashboard

**Cost Intelligence Dashboard for OpenClaw** — Real-time token consumption, cost analysis, and burn rate projections.

---

## 🚀 Daily Startup (run these every time you boot the machine)

Open two terminal tabs and run one command in each:

**Terminal 1 — Backend:**
```bash
cd ~/github/CangreDashboard/backend && bash run.sh
```

**Terminal 2 — Frontend:**
```bash
cd ~/github/CangreDashboard/frontend/public && python3 -m http.server 8000
```

Then open the dashboard in your browser:

```
http://localhost:8000
```

That's it. Leave both terminals running while you work. Backend listens on `:5001`, frontend on `:8000`.

---

## Overview

CangreDashboard is a standalone cost intelligence system built to analyze OpenClaw agent execution and help you implement cost-saving strategies. It reads from your OpenClaw session logs, calculates costs based on configurable pricing tiers, and presents insights through an interactive dashboard.

### Features

✅ **Full History** — Backfills all existing OpenClaw logs (90-day retention)  
✅ **Cost Breakdown** — Costs by agent, model, and time period  
✅ **Burn Rate** — Real-time $/hour and projected daily/monthly spend  
✅ **Timeline** — Chronological view of all agent executions  
✅ **Export** — CSV export for spreadsheet analysis  
✅ **Cost Optimization** — Identify expensive models and agents  

---

## Quick Start (5 minutes)

### Prerequisites

- macOS 10.15+ (or Linux/WSL)
- Python 3.8+
- Running OpenClaw instance

### 1. Clone & Setup Backend

```bash
cd ~/github/CangreDashboard/backend
bash run.sh
```

This will:
- Create a Python virtual environment
- Install dependencies
- Start the backend on `http://localhost:5001`
- Auto-scan OpenClaw logs on startup

Expected output:
```
✓ Config validated
  - OPENCLAW_HOME: /Users/fedeh/.openclaw
  - DB_PATH: /Users/fedeh/.openclaw/cangre_dashboard.db
✓ Database initialized
Starting full scan of OpenClaw sessions...
Full scan complete. Processed 2 agents
🚀 Starting backend server on http://127.0.0.1:5001
```

### 2. Backfill Full History (Optional)

If you want to ensure all existing logs are parsed:

```bash
cd ~/github/CangreDashboard/scripts
bash backfill-history.sh
```

This will:
- Parse all session JSONL files
- Calculate costs for all messages
- Aggregate into daily metrics
- Clean up data older than 90 days

### 3. Open Dashboard

Open your browser to:

```
file:///Users/fedeh/github/CangreDashboard/frontend/public/index.html
```

Or serve it locally:

```bash
cd ~/github/CangreDashboard/frontend/public
python3 -m http.server 8000
# Then open http://localhost:8000
```

---

## Dashboard Features

### 📈 Overview

- **Today's Cost** — Total cost today vs. yesterday with % change
- **Total Tokens** — Token consumption today
- **Active Sessions** — Running sessions count
- **Agent Breakdown** — Per-agent cost and token stats

### 💰 Cost Analysis

- **Token Distribution (Pie Chart)** — Which models consume most tokens?
- **Cost by Model (Bar Chart)** — Which models cost most?

### 🔥 Burn Rate & Projections

- **Cost per Hour** — Current burn rate (last 24h)
- **Projected Daily Cost** — If current rate continues
- **Projected Monthly Cost** — Extrapolated to 30 days
- **Tokens per Hour** — Token burn rate

### ⏱️ Recent Execution Timeline

- Last 50 messages
- Timestamp, agent, model, tokens, cost
- Auto-refreshes every 15 seconds

---

## Cron Jobs: Live Status & Troubleshooting

The Cron Jobs section now shows real-time status for every job, including whether it is running, stuck, finished, or errored. This is done **without polling the agent or burning tokens**.

### How it works
- The backend reads each job's `~/.openclaw/cron/runs/<job_id>.jsonl` file.
- If `jobs.json` shows `lastRunAtMs` newer than the most recent `runAtMs` in that file, the job is currently running.
- If a job is running for more than 3× its typical duration (or >45min with no baseline), it is flagged as **stuck**.
- The dashboard auto-refreshes every 15s, so you see elapsed time live.
- Click the ▸ next to a job name to expand and see the last run's output summary and token usage.

### Status Badges

| Badge | Meaning |
|---|---|
| 🔄 Running · 2h 14m | Currently executing, elapsed time updates live |
| ⚠️ Stuck · 3h 05m | Running >3× typical duration or >45min |
| ✅ Done | Last run succeeded |
| ❌ Error ×2 | Last run failed, with consecutive error count |
| ⚪ idle | Never triggered |

### Example: Socrates Audit
If you launch a long-running audit job (e.g. Socrates), the dashboard will show:
- **🔄 Running** while the job is in progress
- **⚠️ Stuck** if it exceeds expected duration
- **✅ Done** or **❌ Error** when finished

No more guessing or burning tokens to ask for status!

---

## Data & Storage

### Database Location

```
~/.openclaw/cangre_dashboard.db
```

SQLite database with tables:
- `agents` — Agent metadata
- `sessions` — OpenClaw sessions
- `messages` — Individual LLM messages with cost breakdown
- `daily_metrics` — Aggregated daily costs by agent/model

### Data Retention

- **Hot Data:** Last 90 days in SQLite
- **Archive:** Manual export to CSV before cleanup

### Cleanup Old Data

To manually clean up data older than 90 days:

```bash
cd ~/github/CangreDashboard/backend && source venv/bin/activate
python3 -c "from aggregator import cleanup_old_data; cleanup_old_data()"
```

---

## Cost Configuration

### Editing Pricing Tiers

Costs are calculated from token counts using configurable rates. To update pricing:

1. Open `backend/config.py`
2. Find `PRICING_TIERS` dict
3. Update rates ($/1000 tokens):

```python
PRICING_TIERS = {
    'claude-sonnet-4.6': {
        'input': 0.003,              # $0.003 per 1K input tokens
        'output': 0.015,             # $0.015 per 1K output tokens
        'cache_read': 0.0003,        # $0.0003 per 1K cache read
        'cache_write': 0.0003,       # $0.0003 per 1K cache write
    },
    # Add more models as needed
}
```

4. Restart backend:
```bash
# Kill the running server
killall python
# Restart
cd ~/github/CangreDashboard/backend && bash run.sh
```

5. Trigger cost recalculation:
```bash
curl -X POST http://localhost:5001/api/admin/aggregate-costs
```

**When Real Billing Arrives:**  
Once OpenClaw/GitHub enables actual billing, you can query the real costs from their API and return them instead of calculating from rates. The dashboard is designed to accept either approach.

---

## API Endpoints

### Overview & Metrics

```bash
# Today's overview (cost, tokens, active agents)
curl http://localhost:5001/api/overview

# Overall cost summary (all time)
curl http://localhost:5001/api/metrics/summary

# Daily metrics (7-day default)
curl http://localhost:5001/api/metrics/daily?days=7

# Burn rate (default: last 24h)
curl http://localhost:5001/api/cost/burn-rate?window_hours=24
```

### Cost Breakdown

```bash
# Cost by agent
curl http://localhost:5001/api/cost/by-agent

# Cost by model
curl http://localhost:5001/api/cost/by-model

# All agents with stats
curl http://localhost:5001/api/agents
```

### Execution Data

```bash
# Sessions
curl http://localhost:5001/api/sessions?limit=50

# Timeline (last N messages)
curl http://localhost:5001/api/timeline?limit=100
```

### Admin Actions

```bash
# Trigger full rescan of OpenClaw logs
curl -X POST http://localhost:5001/api/admin/rescan

# Trigger cost aggregation
curl -X POST http://localhost:5001/api/admin/aggregate-costs

# Cleanup old data
curl -X POST http://localhost:5001/api/admin/cleanup
```

---

## Export to CSV

Export costs for analysis in Excel or Google Sheets:

```bash
cd ~/github/CangreDashboard/scripts

# Export last 7 days (default)
bash export-costs.sh

# Export specific date range
bash export-costs.sh 2026-04-06 2026-04-13 my_costs.csv
```

Output: CSV with columns: Date, Agent, Model, Tokens, Cost, Messages

---

## Architecture

```
OpenClaw Session JSONL
(~/.openclaw/agents/*/sessions/*.jsonl)
         ↓
   Aggregator (Python)
   - Parse JSONL events
   - Extract token usage
   - Calculate cost (config.PRICING_TIERS)
   - Group by date/agent/model
         ↓
   SQLite Database
   (~/.openclaw/cangre_dashboard.db)
         ↓
   Flask REST API
   (:5001/api/*)
         ↓
   React Dashboard
   (Browser - http://localhost:8000 or file://)
```

### Data Flow

1. **Aggregator** reads JSONL files continuously
2. Extracts `usage` data: input_tokens, output_tokens, cache_tokens
3. Calculates cost using model pricing from `config.PRICING_TIERS`
4. Stores in SQLite with full message history
5. API aggregates into daily metrics on-demand
6. Dashboard queries API every 15s for latest data

---

## File Structure

```
~/github/CangreDashboard/
├── backend/
│   ├── app.py                 # Flask REST API server
│   ├── schema.py              # SQLAlchemy ORM models
│   ├── aggregator.py          # JSONL parser + importer
│   ├── cost_analyzer.py       # Cost calculation engine
│   ├── config.py              # Pricing tiers + settings
│   ├── requirements.txt       # Python dependencies
│   ├── run.sh                 # Startup script
│   └── venv/                  # Virtual env (created on first run)
├── frontend/
│   ├── public/
│   │   └── index.html         # Complete React app (CDN-based)
│   └── src/
│       └── index.css          # Styling
├── scripts/
│   ├── backfill-history.sh    # Full history scan
│   └── export-costs.sh        # CSV export
├── docs/
│   └── ARCHITECTURE.md        # (future: detailed design)
└── README.md                  # This file
```

---

## Troubleshooting

### ❌ "Unable to connect to backend"

**Check backend is running:**
```bash
ps aux | grep "app.py"
```

**Restart backend:**
```bash
cd ~/github/CangreDashboard/backend && bash run.sh
```

**Check logs:**
```bash
# Terminal where backend was started
# Look for error messages
```

---

### ❌ "No data showing in dashboard"

**Run backfill:**
```bash
cd ~/github/CangreDashboard/scripts && bash backfill-history.sh
```

**Check database:**
```bash
sqlite3 ~/.openclaw/cangre_dashboard.db
sqlite> SELECT COUNT(*) FROM messages;
```

**Check OpenClaw logs exist:**
```bash
ls -la ~/.openclaw/agents/*/sessions/*.jsonl
```

---

### ❌ "Costs showing as $0"

This is normal! Until OpenClaw/GitHub enables billing, all costs are calculated from `config.PRICING_TIERS`. The dashboard structure is ready for real billing:

1. Update rates in `config.py` when you know real pricing
2. Or modify `cost_analyzer.py` to query billing API
3. Restart backend and trigger `POST /api/admin/aggregate-costs`

---

### ❌ "Database locked" error

SQLite has only one writer at a time. If you see lock errors:

1. Stop backend
2. Delete database: `rm ~/.openclaw/cangre_dashboard.db`
3. Restart backend (will rebuild)

---

## Cost Optimization Strategies

Once dashboard is running, use it to answer:

1. **Which agent is most expensive?**
   → Look at "Agent Breakdown" overview tile
   
2. **Which model costs most?**
   → See "Cost by Model" bar chart
   
3. **What's our burn rate?**
   → Check "Burn Rate & Projections" section
   
4. **Can we switch agents to cheaper models?**
   → Export data, compare token counts vs. costs
   
5. **Are cache tokens reducing cost?**
   → Look at daily metrics; compare cache_write to cost_savings

### Next Steps (Phase 2)

Once you identify expensive patterns:

1. **Create cost optimization rules** in agent config
   - "Use GPT-4 only for complex tasks"
   - "Cache markdown files to reduce input tokens"
   - "Batch similar requests to reuse cache"

2. **Set budget alerts**
   - Slack notification if daily cost > $X
   - Pause agent if monthly projection > budget

3. **A/B test models**
   - Run Bernardo with Claude vs. GPT
   - Compare token efficiency in dashboard

---

## Contributing & Feedback

This is v1.0 MVP. Future versions (Phase 2+):

- [ ] WebSocket live-feed for real-time updates
- [ ] Budget alerts & auto-pause
- [ ] A/B model comparison tool
- [ ] Cost optimization recommendations
- [ ] Multi-user access (auth)
- [ ] Historical trend analysis (ML-based)
- [ ] Integration with GitHub billing API
- [ ] Dockerized deployment

---

## License

MIT (or choose your license)

---

## Questions?

Check the docs:
- `docs/ARCHITECTURE.md` — Detailed design
- API endpoints above → curl examples
- Backend logs → `~/.openclaw/cangre_dashboard.db`

Happy cost optimizing! 🦞
