# PricePilot AI

[![CI](https://github.com/RaghavaAlajangi/pricepilot-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/RaghavaAlajangi/pricepilot-ai/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/RaghavaAlajangi/pricepilot-ai?label=deployed&color=blue)](https://github.com/RaghavaAlajangi/pricepilot-ai/releases/latest)
[![Coverage](https://codecov.io/gh/RaghavaAlajangi/pricepilot-ai/branch/main/graph/badge.svg)](https://codecov.io/gh/RaghavaAlajangi/pricepilot-ai)
[![Agent Regression](https://github.com/RaghavaAlajangi/pricepilot-ai/actions/workflows/agent-regression.yml/badge.svg)](https://github.com/RaghavaAlajangi/pricepilot-ai/actions/workflows/agent-regression.yml)

**Live demo:** [Frontend](https://pricepilot-ai-pi.vercel.app/) · [API docs](https://pricepilot-ai-pi.vercel.app/docs)

Proof of concept for **ML- and AI-agent-supported pricing decisions** at a
European lighting e-commerce group. It analyses two years of daily sales
(60 products × 6 categories × 3 markets), estimates the price-demand
relationship per product/market, derives a profit-optimal price, and lets a
team of three AI agents interpret the result — with automated checks on what
the agents say.

## Contents

- [Design](#design)
  - System overview, data layer, caching, API surface
- [ML approach](#ml-approach)
  - Log-log linear regression (elasticity), three-tier model strategy,
    offline training
- [Agent approach](#agent-approach)
  - Multi-step sequential pipeline: Analyst → Strategist → Reviewer
- [Guardrails](#guardrails)
  - Input validation, code-level safety and grounding checks on agent output
- [Evaluation — agent regression tests](#evaluation--agent-regression-tests)
  - Lightweight checks: offline pytest suite on every PR, live-LLM
    evaluation on main and before deploys
- [Trade-offs](#trade-offs)
  - What was kept deliberately simple, and why
- [Limitations](#limitations)
  - Operational and modelling limitations, stated honestly
- [Running the app](#running-the-app)
  - Docker Compose, `.env` setup, hot-reload with `compose watch`, tests
- [Deployment](#deployment)
  - Vercel (frontend) + Render (backend) via tagged releases
- [Deliverables](#deliverables)
  - Challenge requirement → where it is implemented

## Design

Two containers, one repo. The frontend never talks to the LLM — every AI
call goes through the backend, where guardrails and logging live.

```
frontend   Next.js 14 + Tailwind + Recharts          (port 3000)
    │  REST /api/v1  (agent endpoints require X-API-Key)
backend    FastAPI                                    (port 8000)
    ├── data_source.py       CSV in memory (Postgres optional via env)
    ├── ml/elasticity.py     tiered elasticity models + live OLS fallback
    ├── agents/graph.py      LangGraph: Analyst → Strategist → Reviewer
    ├── guardrails.py        price-safety + number-grounding checks
    └── cache.py             in-memory TTL cache (cachetools)
train/     offline training script → .joblib weights in data/weights/
```

<details>
<summary><strong>Read more — design decisions</strong></summary>

- **Data layer is a two-method Protocol** (`list_products`,
  `product_series`) with a CSV and a Postgres implementation. The PoC runs
  entirely from the bundled CSV in memory; setting `DATABASE_URL` switches
  to Postgres without touching any other code.
- **Train/serve split.** `train/train.py` fits the models offline and
  writes `.joblib` weight bundles; the backend only loads weights and
  predicts. This keeps API latency low and mirrors how a production
  batch-training pipeline would hand off to a serving layer.
- **Caching is a process-local TTL cache** (`cachetools.TTLCache`, 24 h TTL)
  keyed by product/market/model. Agent runs cost API tokens, so repeat
  requests are served from cache. A previous Redis-based cache was removed —
  a single-process deployment doesn't need a network hop for caching.
- **API surface** (`/api/v1`): product catalogue, per-product summary
  (KPIs + weekly series), elasticity results (incl. full profit curve), and
  two agent endpoints — a plain POST and a Server-Sent-Events stream that
  emits per-agent progress with latency and token usage (shown live in the
  UI).
- **Configuration** is entirely environment-based (`pydantic-settings`,
  see `.env.example`). Missing/invalid config fails at startup with a clear
  error; `/health` returns `200 OK` for container health checks.
- **Logging** is structured JSON (structlog): every agent run logs model,
  input hash, latency, and guardrail status. No print statements.

</details>

## ML approach

A deliberately **simple linear regression** in log space: the price
coefficient of `ln(units) ~ ln(price) + controls` *is* the price
elasticity. It is fast enough to run interactively, and every coefficient
can be explained to a business stakeholder.

<details>
<summary><strong>Read more — model spec and the three-tier strategy</strong></summary>

**Feature engineering** (identical in training and serving):

1. **Aggregate daily → weekly.** A large share of daily rows have zero
   sales; weekly totals smooth that noise into ~104 clean observations per
   product/market.
2. **Log-log regression:**
   `ln(units) = a + e·ln(price) + b·ln(ad_spend+1) + month dummies`.
   Ad spend and month dummies absorb promotion/seasonality effects — Black
   Friday weeks have low prices *and* high ads, so without the controls the
   elasticity estimate would be biased.
3. **Optimal price:** predict weekly demand on a 50-point price grid
   strictly inside the observed price range (no extrapolation), pick the
   price that maximises `(price − cost) × predicted units`.

**Three tiers**, trained offline by `train/train.py`, loaded at request
time by `backend/app/ml/elasticity.py`:

| Tier | Scope | Model | Why |
|---|---|---|---|
| 1 | High-volume SKUs (top ~50% of revenue), per SKU × market | OLS | Enough data per SKU for a dedicated fit |
| 2 | Mid-volume SKUs, pooled per category × market | Ridge with SKU dummies | Pooling borrows strength where per-SKU data is thin |
| 3 | Anything without a saved weight file | Live OLS fit on raw data | Always-available fallback; also used in tests |

The API returns elasticity, R², the full profit curve, a confidence label
(high/medium/low based on sign and fit), and explicit warnings (inelastic
demand, edge-of-range optimum, low R²).

**Retraining:** `python train/train.py --dataset data/dataset.csv
--weights-dir data/weights`. The script's docstring documents the intended
production evolution (orchestrated DAG, artefact store, model registry) —
out of scope here.

</details>

## Agent approach

A **multi-step sequential pipeline** — a deterministic, linear LangGraph
with three roles and no LLM-driven routing:

```
Analyst  →  Strategist  →  Reviewer
```

| Agent | Role | Output schema |
|---|---|---|
| Data Analyst | translates the ML result into plain business language | `AnalystFindings` |
| Pricing Strategist | recommends one price with rationale, impact, risks | `StrategistRecommendation` |
| Risk Reviewer | verdict `approve/revise/reject` with explicit checks | `ReviewerVerdict` |

<details>
<summary><strong>Read more — why linear, prompts, cost control</strong></summary>

- **Linear graph, no branching.** For a pricing recommendation there is no
  routing decision an LLM should make; determinism keeps latency, cost, and
  audit trails predictable. "Complexity does not mean better."
- **Structured output everywhere** (Pydantic schemas on every node) — no
  free-text parsing anywhere downstream.
- **Compact numeric payload** (~16 fields, no raw rows) — three LLM calls of
  a few hundred tokens each per analysis; results cached for 24 h.
- **Streaming telemetry:** the SSE endpoint emits `step_started` /
  `step_completed` per agent with latency and token counts, which the UI
  renders live.
- Prompts live in `backend/app/agents/prompts.py` as named constants; every
  prompt forbids inventing numbers not present in the payload.
- Agent state is a typed `TypedDict`; each node records an
  `AgentStepStats` entry.

</details>

## Guardrails

Simple, code-level guardrails — no external guardrail framework:

- **Input:** every request is validated by Pydantic (SKU pattern, market
  enum) before reaching any model or agent; agent endpoints additionally
  require an `X-API-Key` header.
- **Output:** after the agents run, `backend/app/guardrails.py` checks the
  recommendation *in code* — the LLM reviewer is a second opinion, not the
  safety net.

<details>
<summary><strong>Read more — the actual checks, and when they run</strong></summary>

**At request time** — `validate_recommendation` (safety) runs on every
live agent response:

- recommended price must clear **cost + 2%**
- must stay within **±30% of the current price**
- must lie within the **observed price range ±10%** (no extrapolated prices)

Violations don't block the response — they are returned in a
`GuardrailReport` and shown as a red banner in the UI, so a category
manager sees exactly *why* a recommendation is suspect. Failures are also
logged with the run's metadata.

**Before deployment** — `ungrounded_numbers` (grounding) is enforced in
CI by the [agent evaluation](#evaluation--agent-regression-tests): every
number ≥ 10 cited in agent text must match a number in the agent's input
payload within **±5%**, otherwise it is flagged as ungrounded. The offline
suite exercises the check logic on every PR; the live evaluation applies
it to real LLM output when agent code changes on `main` and as a deploy
gate.

</details>

## Evaluation — agent regression tests

The lightweight evaluation required by the challenge runs in two layers,
sharing the same four checks:

- **Offline regression suite** (`backend/tests/test_agent_eval.py`, marker
  `agent`) — simulated agent output, no API key, runs on every PR and push.
- **Live evaluation** (`backend/scripts/evaluate_agents.py`) — runs the
  real LLM workflow over 3 example cases and applies the checks to what
  the agents actually said; runs in CI when LLM-facing code changes and
  as a gate before every deployment.

```bash
cd backend
DATASET_PATH=../data/dataset.csv pytest tests -m agent -v      # offline
DATASET_PATH=../data/dataset.csv python -m scripts.evaluate_agents  # live (needs OPENAI_API_KEY)
```

<details>
<summary><strong>Read more — the four checks and the CI gate</strong></summary>

Four checks per example case (3 product/market cases):

| Check | What it verifies |
|---|---|
| **Structure** | agent output parses into the response schema |
| **Grounding** | every number an agent cites appears in its input payload (±5%) |
| **Safety** | recommendation is above cost, plausible vs current price, inside the observed range |
| **Consistency** | the reviewer must not approve a recommendation that fails guardrails |

Negative tests inject deliberately bad output (an invented competitor
price, a below-cost recommendation) and assert the checks *fire* — proving
the evaluation can actually detect failures, not just pass.

**Why two layers:** the offline suite is deterministic and free, so it can
run on every PR — it protects the check logic and the ML pipeline from
regressions. The live evaluation is the part the brief actually describes
(sanity-checking what the agents say), so it runs where real output
matters, at roughly nine small LLM calls per run.

`.github/workflows/agent-regression.yml` runs the offline suite on every
PR and push (with `scripts/check_regression.py` blocking if the pass rate
drops more than 2%). The live evaluation is conditional: a paths filter
triggers it only when a push to `main` touches LLM-facing code (agents,
prompts, guardrails, schemas, the eval script, or pinned dependencies) —
doc or frontend changes don't burn API tokens. It can also be started
manually from the Actions tab. `deploy.yml` runs both as gates before
deploying — a release tag will not ship if real agent output fails a
check.

This is intentionally *not* an evaluation framework — a handful of
deterministic checks over a few example cases, which is what the task asks
for.

</details>

## Trade-offs

Every simplification below was a deliberate choice for a PoC, with the
production alternative known and noted.

<details>
<summary><strong>Read more — what was kept simple, and what the alternative was</strong></summary>

| Chose | Instead of | Because |
|---|---|---|
| Log-log linear regression | XGBoost / Bayesian models | Interpretable coefficient *is* the elasticity; fast enough to run interactively; complexity ≠ better |
| Linear 3-agent pipeline | Router/supervisor patterns, tool-calling agents | No branching decision exists here; determinism keeps latency, cost, and audits predictable |
| In-memory TTL cache | Redis | Single-process deployment; a network cache adds ops burden with no benefit at this scale |
| CSV loaded in memory | Postgres (still supported via `DATABASE_URL`) | 131k rows fit comfortably in memory; removes a service from the free-tier deployment |
| pytest regression suite | Eval framework / dashboard | The task asks for the instinct to verify, not tooling sophistication |
| Structured JSON logs only | LangSmith / OpenTelemetry tracing | Observability stack is overkill for a PoC; logs already capture model, input hash, latency, guardrail status |
| Vercel + Render | Google Cloud Run (suggested in the brief for its free tier) | Equally free, and needs no billing-enabled cloud account; the app is container-based, so moving to Cloud Run later is a workflow change, not a code change |

</details>

## Limitations

This is a **simple setup by design** — a PoC, not a production system.

<details>
<summary><strong>Operational limitations</strong></summary>

- **Agent analyses are not persisted.** Results live in an in-process cache
  (24 h TTL) and vanish on restart; there is no history of past
  recommendations.
- **No dedicated database or caching layer.** The dataset is a CSV in
  memory and the cache is process-local. Fine for one instance; horizontal
  scaling would need shared state.
- **No rate limiting.** The agent endpoints are protected by an API key,
  but nothing throttles repeated calls (each of which costs LLM tokens).
- **No observability stack.** Structured logs only — no tracing, no
  metrics endpoint, no LLM-call dashboards.
- **Free-tier deployment (Vercel + Render).** The Render backend cold-starts
  after idle periods, so the first request after a quiet spell can take up
  to a minute.
- **Simple UI.** One dashboard page: product/market selectors, KPI cards,
  charts, and the agent panel. No auth, no user management, no saved views.
- **Single LLM provider** (OpenAI via env config); no automatic fallback
  provider.

</details>

<details>
<summary><strong>Modelling limitations</strong></summary>

- **Observational elasticity, not causal.** Prices weren't randomised; ad
  spend and month controls reduce but don't eliminate confounding. A/B
  price tests would be the next step before trusting the numbers
  operationally.
- **Constant-elasticity assumption.** One log-log slope per product/market;
  no cross-product cannibalisation, no competitor prices (not in the data).
- **No extrapolation beyond observed prices** — a safety feature, but the
  "optimal" price can sit at the range edge (the app flags this).
- **`web_sessions` is deliberately unused:** sessions are partly a
  *consequence* of price (via ad-driven promo traffic), so including them
  would absorb part of the price effect (mediator bias).
- **Missing `ad_spend` (~15% of rows) is treated as zero** — reasonable for
  paid-marketing data, but unverified.
- **Agent output is advisory.** Guardrails check plausibility, not truth;
  the human-in-the-loop is the category manager reading the dashboard.

</details>

## Running the app

```bash
cp .env.example .env     # fill in OPENAI_API_KEY (and APP_API_KEY)
docker compose up --build
```

Open **http://localhost:3000**. The backend API (with OpenAPI docs) is at
http://localhost:8000/docs. Everything works without an API key except the
"Run AI analysis" button.

<details>
<summary><strong>Read more — hot reload, tests, training</strong></summary>

**Hot reload during development** (uses the `develop.watch` config in
`docker-compose.yml` — backend and frontend code is synced into the running
containers):

```bash
docker compose watch
```

**Backend tests** (schemas, guardrails, ML sanity, agent graph with a fake
LLM, API integration, agent regression):

```bash
cd backend
pip install -r requirements-dev.txt
DATASET_PATH=../data/dataset.csv pytest tests -v
```

**Retrain the model weights** (writes `.joblib` bundles to
`data/weights/`, which the backend picks up):

```bash
python train/train.py --dataset data/dataset.csv --weights-dir data/weights
```

**Key environment variables** (full list with comments in `.env.example`):

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | enables the agent endpoints (backend only — never exposed to the browser build beyond the app key) |
| `OPENAI_MODEL` | LLM used by the agents (default `gpt-4o-mini`) |
| `APP_API_KEY` / `NEXT_PUBLIC_APP_API_KEY` | shared key the frontend sends as `X-API-Key` to agent endpoints |
| `NEXT_PUBLIC_API_URL` | backend base URL for the frontend |
| `FRONTEND_ORIGINS` | comma-separated CORS allow-list |
| `DATASET_PATH` / `DATABASE_URL` | CSV mode (default) or Postgres mode |

</details>

## Deployment

Pushing a version tag (`v*.*.*`) triggers `.github/workflows/deploy.yml`:
CI (lint, tests, frontend build) and the agent regression gate must pass,
then the **backend deploys to Render** and the **frontend to Vercel**.

<details>
<summary><strong>Read more — required secrets</strong></summary>

Repository secrets: `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`,
`RENDER_API_KEY`, `RENDER_SERVICE_ID`. The workflow header documents where
each one comes from. Runtime configuration (API keys, CORS origins) is set
in the Render/Vercel dashboards, mirroring `.env.example`.

The brief suggests Google Cloud Run because its free tier makes deployment
cost nothing; Vercel + Render achieves the same at zero cost, without
needing a billing-enabled Google Cloud account. Since both services run
plain containers/builds, switching to Cloud Run is a CI workflow change
only.

</details>

## Deliverables

Mapping the challenge objectives to this repo:

| Requirement | Where |
|---|---|
| Interactive data visualization | Next.js dashboard — price vs. sales, weekly trends, per-product/market views (Recharts) |
| ML model of price-demand + optimal prices, visualised | [ML approach](#ml-approach); elasticity, profit curve, and recommended price rendered in the dashboard |
| Multiple AI agents with distinct roles | [Agent approach](#agent-approach) — Analyst → Strategist → Reviewer (LangGraph) |
| Lightweight evaluation of agent output | [Evaluation](#evaluation--agent-regression-tests) — grounding, safety, structure, consistency checks; offline on every PR, against real LLM output before deploys |
| Public GitHub repo, deployed frontend + backend | This repo; frontend on Vercel, backend on Render (links shared separately) |
