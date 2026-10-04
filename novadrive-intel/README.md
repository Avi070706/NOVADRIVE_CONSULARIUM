# NovaDrive Supply Intelligence

A decision-support platform for NovaDrive's CRO/CPO: it reconstructs the Tier-1 to Tier-3 supplier network from
the case workbook, scores risk and confidence separately, triages external signals, and screens alternate suppliers,
with every conclusion traceable to its source records.

## Run

```
pip install -r requirements.txt
python run.py                 # open http://localhost:8000
```

The frontend is already compiled into `backend/static`, so Node is not needed to run it.
To change the UI: `cd frontend && npm install && npm run dev` (dev server on :5173, proxies `/api` to :8000),
then `npm run build` to refresh `backend/static`.

## Deploy on Vercel

The project is Vercel-ready: `vercel.json` serves the pre-built UI as static files and runs the FastAPI backend as a Python function (`api/index.py`). No build step is needed.

1. Put this folder in a GitHub repo, then on vercel.com choose **Add New → Project**, import the repo, set Framework to **Other**, and deploy. Or, from this folder: `npm i -g vercel` then `vercel --prod`.
2. Optional environment variables (Project → Settings → Environment Variables), then redeploy:

| Variable | Purpose |
|---|---|
| `WORKBOOK_URL` | Live Excel link (see below). Without it, the bundled `data/NovaDrive.xlsx` is used. |
| `WORKBOOK_TTL` | Seconds between checks of the cloud workbook (default 30). |
| `TAVILY_API_KEY` or `BRAVE_API_KEY` | Enables live web search on the Sourcing page. |

**Live Excel on Vercel.** Serverless functions have no persistent disk, so edit the workbook in the cloud instead:

1. Upload `NovaDrive.xlsx` to Google Drive and open it with Google Sheets.
2. Share it as *Anyone with the link: Viewer*.
3. Set `WORKBOOK_URL` to `https://docs.google.com/spreadsheets/d/<SHEET_ID>/export?format=xlsx`.

Edits then appear on the dashboard within about 30 seconds, with the change notification. A OneDrive or SharePoint direct-download link also works. If the link fails, the app falls back to the bundled copy.

On Vercel, **Replace workbook** only lasts until the function restarts; use `WORKBOOK_URL` for lasting changes.

## Your figures are displayed as entered

Sheets starting with `DB ` in the workbook hold the team's figures. The dashboard shows them exactly as entered and never recalculates them:

| Sheet | Drives |
|---|---|
| DB Headline | Title, subtitle, the three headline metrics, tagline, the three exposure nodes |
| DB Scorecard | Risk score, evidence grade (A–D) and reading for all 25 nodes |
| DB Weights | The seven factor weights shown on the Risk page |
| DB Signals / DB Alert Briefs | Naive vs our reading, verdict, alert priority, and the What / Why / Next action briefs |
| DB Priorities | The decisions list on the Situation page (action, nodes, why) |
| DB Alternates / DB Sourcing Brief | Candidate cards (fit 0–5, risk, footprint, evidence, source link), search spec, validation checklist, fit framework |

The engine still reconstructs the network, exposure paths, signal matching and evidence trail from the six case sheets around those numbers.

## Linked to Excel

`data/NovaDrive.xlsx` is watched. Save the file (or use **Replace workbook** in the left rail) and within about
two seconds the network, scores, alerts, action queue and headline are rebuilt. A notification lists what changed,
for example "Meridian Dielectrics risk 64 → 46" or "New signal EV-011: alert". If a save is half-written or a sheet is
broken, the app keeps showing the last good version and says so. Use another file with `NOVADRIVE_XLSX=path`.

Sheets and columns are found by keyword, so renaming or reordering columns is tolerated. Relationship Evidence is
parsed by sentence pattern (`backend/engine/network.py`). Any record the parser does not understand is shown as
"Not parsed" on the Evidence page instead of being dropped silently.

## The journey

| Page | Shows |
|---|---|
| Situation | Decisions needed (with reason, exposure, linked signals), live signals, convergence diagram, highest risks, products at stake, dual-sourcing check |
| Network | Tier-3 → products map in the deck's colours; filter by product, switch to zone view, click to trace |
| Risk | 25-node scorecard, risk vs evidence-grade chart, scoring weights |
| Signals | Naive vs our reading for each signal, alert brief, test a new signal |
| Sourcing | Ranked alternate candidates with fit and risk, fit-vs-risk chart, validation checklist, live search |
| Evidence | Six checks; full tables: rejected and unresolved ledger (18 items), data traps, all 31 links, all 59 records; record-level trace for each chokepoint |

Any supplier, component, issue or candidate opens the inspector (summary, risk drivers, evidence). Ctrl/⌘ K searches everything.

## Method

**Network.** Links come only from Relationship Evidence, never from the Supplier Universe:

- Award, qualification and input disclosures create **confirmed** links.
- A customer listing creates an **inference** (Verdant → IonPeak).
- A sample evaluation creates a **hypothesis** (Solace → Grove).

Expired awards, look-alike names, intermediaries, pilot sites and trade-directory leads are listed as ruled out or unresolved.

**Relationship confidence** adds points per independent source family:

| Evidence kind | Points |
|---|---|
| Award or input disclosure | 50 |
| Qualification record | 35 |
| Technical statement | 20 |
| Shipment | 15 |
| Shipment via intermediary | 10 |

Records from the same family count once, and the total is capped at 100. Inference is capped at 45 and hypothesis at 20.

**Risk** combines seven factors (0–100), each stored with a written reason. Default weights:

| Factor | Weight |
|---|---|
| Business criticality | 20% |
| Concentration | 15% |
| Network dependence | 15% |
| Substitution difficulty | 15% |
| Financial health | 15% |
| Operational | 10% |
| Geography | 10% |

Missing indicators score 60 and lower confidence; missing is never treated as safe. When a node is the only *observed* supplier of an input, but no record states it is the sole source, its share counts at 80%.

**Assessment confidence** = 65% weakest-link evidence on the best path to NovaDrive + 35% data completeness.

**Decision** combines both:

| Risk | Confidence | Decision |
|---|---|---|
| 65+ | 60+ | Act now |
| 65+ | Below 60 | Verify first |
| 50–64, or an active signal | Any | Monitor |

Acute financial or operational stress behind 50%+ of revenue overrides to act or verify.

**Signals** pass seven gates:

1. Freshness: stale re-posts are suppressed.
2. Duplicate check: same source family is merged.
3. Entity resolution: place names are stripped first so "East Delta" cannot match "Delta …"; negations and registry IDs are honoured.
4. Facility and geography: zone names are learned from the evidence text; office-only events are treated as information.
5. Network traversal.
6. Exposure.
7. Decision.

Impact wording distinguishes a confirmed disruption from exposure only.

## Web search

`backend/search/providers.py` tries providers in order. A failing provider is skipped for two minutes, and results are cached in `data/search_cache.json`.

| Order | Provider | Requirement |
|---|---|---|
| 1 | Tavily | `TAVILY_API_KEY` |
| 2 | Brave | `BRAVE_API_KEY` |
| 3 | SerpAPI | `SERPAPI_API_KEY` |
| 4 | DuckDuckGo | None — installed by default (`ddgs`); unofficial, can be rate-limited |
| 5 | Wikipedia API | None (keyless) |
| 6 | GDELT news | None (keyless) |

Live search therefore works without any API key wherever the server has internet access. A free Tavily key (sign up at tavily.com, about 1,000 searches a month at the time of writing) gives the most reliable results.

If all fail, the UI says so and shows the last cached live result, or none. No result is ever invented.

`backend/search/snapshot.json` is an **analyst research snapshot** gathered with live web search on 2026-10-04:

- **SiC dies:** Wolfspeed, Bosch, onsemi.
- **PCB substrates:** AT&S, Best Technology.
- **Capacitor film:** Toray, Dongfang.

Notes are short paraphrases with links, so the sourcing workflow can be demonstrated offline. It is clearly labelled in the UI, and any entry can be removed or added.

**Candidate assessment** has two separate parts:

- **Technical fit:** six weighted criteria, each scored from terms found in the sources, with the source cited.
- **Risk screen:** financial, operational, geographic and evidence-quality signals, each low, elevated, high or unknown.

Status can reach *desk-screened* at most. *Qualified* requires NovaDrive engineering validation and is never set from public data.

## Assumptions and limits

- Case data is dated as of the latest record (2025-09-30); freshness is judged against that date, not today.
- Revenue "at stake" is dependency, not forecast loss. No spend, inventory or purchase-order data exists in the case.
- Scores are transparent heuristics, not calibrated probabilities; weights are adjustable in the Risk view.
- Public evidence about real companies is a screening aid, not a qualification.
