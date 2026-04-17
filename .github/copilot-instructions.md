# CangreDashboard — Copilot Agent Instructions

You are the dedicated AI coding agent for **CangreDashboard**, a real-time cost intelligence dashboard for OpenClaw agents. You have full ownership of this codebase. Your primary responsibility is to make changes that are correct the first time — a broken layout means the user sees only a blank page with no error feedback.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Babel standalone (CDN), single file: `frontend/public/index.html` |
| Backend | Flask + SQLite, entry point: `backend/app.py` |
| Charts | Recharts (CDN) |
| HTTP client | Axios (CDN) |
| Build step | **None** — Babel compiles JSX in the browser at runtime |

After any frontend edit, sync with:
```bash
cp frontend/public/index.html frontend/build/index.html
```

---

## The single most important rule

**A single JSX syntax error or undefined variable reference causes the entire page to go blank.** The user sees only the background color. There is no console popup, no error overlay. The only diagnostic is opening DevTools.

Because of this, every edit must be verified before delivery. Read before you write.

---

## Before every edit — mandatory checklist

1. **Read the full target zone** — at minimum 50 lines before and after any line you plan to touch.
2. **Read the full `Dashboard` function** — from `function Dashboard()` to its closing `}`. It is ~250 lines. Know its complete state and render tree before changing anything.
3. **Confirm you are not inside a commented-out block** — lines between `{/*` and `*/}` look like JSX but are inert. Editing them does nothing visible.

---

## File structure

```
frontend/public/index.html
└── <script type="text/babel">
    │
    ├── BudgetGauge({ monthCost, periods, loading })
    ├── MilestonesPanel({ milestones, onDelete, onAdd, onCompare, compareTarget })
    ├── Overview({ overview, loading, onRefresh })        ← defined but NOT rendered (kept for reference)
    ├── AgentBreakdown({ overview, loading, onRefresh })  ← rendered in Dashboard
    ├── CostBreakdown({ models, summary, loading })       ← defined but NOT rendered
    ├── BurnRate({ burnRate, loading })
    ├── PromptCostAnalysis({ promptCosts, loading })
    ├── Recommendations({ promptCosts, onDrillItem, onRefresh })
    ├── Timeline({ timeline, loading })
    ├── BaselineDelta({ current, baseline })
    ├── DrillModal({ item, onClose })
    ├── CronJobs()
    │
    └── Dashboard()
        ├── ~20 useState declarations   ← NEVER touch partially
        ├── 2 useEffect hooks
        ├── error render guard
        └── return JSX:
            └── dashboard-container
                ├── dashboard-header
                └── dashboard-content
                    ├── <section> 💸 Budget          (key: budget)
                    ├── <section> 👥 Agent Breakdown  (key: agents)
                    ├── <section> ⏰ Cron Jobs        (key: cron)
                    ├── <section> 🔥 Burn Rate        (key: burn)
                    ├── <section> 🏁 Milestones       (key: milestones)
                    ├── <section> 🧠 Cost By Prompt   (key: prompt)
                    ├── <section> ⏱️ Timeline         (key: timeline)
                    ├── footer div
                    └── {drillItem && <DrillModal />}
```

---

## Dashboard state — always preserve in full

The `Dashboard` function must always declare all of these state variables. **If your patch touches the state block, include every declaration in your replacement — never partially overwrite it.**

```js
const [open, setOpen] = React.useState({ budget: true, agents: true, cron: true, burn: true, milestones: true, prompt: true, timeline: true });
const toggle = (key) => setOpen(o => ({ ...o, [key]: !o[key] }));
const [overview, setOverview] = useState(null);
const [models, setModels] = useState([]);
const [summary, setSummary] = useState(null);
const [timeline, setTimeline] = useState([]);
const [burnRate, setBurnRate] = useState(null);
const [promptCosts, setPromptCosts] = useState(null);
const [monthCost, setMonthCost] = useState(null);
const [periods, setPeriods] = useState([]);
const [milestones, setMilestones] = useState([]);
const [compareTarget, setCompareTarget] = useState(null);
const [promptAgentId, setPromptAgentId] = useState('');
const [promptStartDate, setPromptStartDate] = useState('');
const [promptEndDate, setPromptEndDate] = useState('');
const [loading, setLoading] = useState(true);
const [error, setError] = useState(null);
const [repeatedOnly, setRepeatedOnly] = useState(false);
const [baseline, setBaseline] = useState(null);
const [drillItem, setDrillItem] = useState(null);
const [refreshKey, setRefreshKey] = useState(0);
```

---

## How to add a new section

1. Create a **new standalone component function** defined before `function Dashboard()`. It handles its own local state.
2. Add its key to the `open` state object (e.g. `mySection: true`).
3. Add a `<div className="section">` block in the Dashboard return using this exact pattern:

```jsx
<div className="section">
    <h2 className="section-title" style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
        <span>🔤 Section Title</span>
        <button onClick={()=>toggle('mySection')} style={{background:'none',border:'none',color:'#00bcd4',fontSize:'1.1rem',cursor:'pointer'}}>{open.mySection ? '▾' : '▸'}</button>
    </h2>
    {open.mySection && <MyComponent prop={value} />}
</div>
```

4. Never put complex JSX logic directly in the Dashboard return. Logic belongs in the component function.

---

## How to hide a section

Replace the entire `<div className="section">...</div>` block with a single one-liner comment:

```jsx
{/* SectionName section is hidden */}
```

**Do not wrap an existing block in `{/* */}`.** Delete it and replace with the one-liner. This is the only safe pattern.

---

## How to move content between sections

1. Create a new component with the content to move.
2. Render it at the new location.
3. Remove the original render site.
4. Never copy JSX from inside a commented-out block — it may contain broken references.

---

## CRITICAL: JSX comments cannot be nested

`{/* */}` comments cannot contain other `{/* */}` comments. The first `*/}` encountered closes the outer comment — everything after it until the next `*/}` is treated as live JSX.

❌ This silently breaks the page:
```jsx
{/*
    <SomeSection />
    {/* this inner comment closes the outer one */}
    <div>{undefinedVar}</div>   ← now live code, crashes component
*/}
```

✅ Always use a single one-liner instead:
```jsx
{/* SectionName section is hidden */}
```

---

## After every frontend edit — verification

Run this grep and check the output:
```bash
grep -n "toggleSessions\|showSessions\|activeSessions\|sessionsLoading" frontend/public/index.html
```

All matches must be inside the `Overview` or `AgentBreakdown` component functions (before line ~400). If any appear inside the `Dashboard` return block (after line ~1020), you have orphaned live JSX from a broken comment — remove it before syncing.

Then always sync:
```bash
cp frontend/public/index.html frontend/build/index.html
```

---

## Backend conventions

- All endpoints are prefixed `/api/`
- CORS is open (dev only)
- SQLite DB path comes from `config.py`
- Background tasks use plain `threading.Thread`
- Never delete `Agent` records — only mark stale
