# PricePilot AI

[![CI](https://github.com/RaghavaAlajangi/pricepilot-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/RaghavaAlajangi/pricepilot-ai/actions/workflows/ci.yml)
[![Deploy](https://github.com/RaghavaAlajangi/pricepilot-ai/actions/workflows/deploy.yml/badge.svg)](https://github.com/RaghavaAlajangi/pricepilot-ai/actions/workflows/deploy.yml)
[![Coverage](https://codecov.io/gh/RaghavaAlajangi/pricepilot-ai/branch/main/graph/badge.svg)](https://codecov.io/gh/RaghavaAlajangi/pricepilot-ai)
[![Agent regression](https://github.com/RaghavaAlajangi/pricepilot-ai/actions/workflows/ci.yml/badge.svg?label=agent-regression&event=push)](https://github.com/RaghavaAlajangi/pricepilot-ai/actions/workflows/ci.yml)

Proof of concept for **ML- and AI-agent-supported pricing decisions** at a
European lighting e-commerce group. It analyses two years of daily sales
(60 products × 6 categories × 3 markets), estimates the price-demand
relationship per product/market, derives a profit-optimal price, and lets a
team of three AI agents interpret the result — with automated checks on what
the agents say.

## Quickstart (Docker)

```bash
cp .env.example .env          # then put your OpenAI API key in .env
docker compose up --build
```

Open **http://localhost:3000**. The backend API (with OpenAPI docs) is at
http://localhost:8000/docs. Everything works without an API key except the
"Run AI analysis" button.

## Architecture

```
frontend  (Next.js 14 + Tailwind + Recharts, port 3000)
    │  REST /api/v1
backend   (FastAPI, port 8000)
    ├── data_source.py   Postgres (compose) or in-memory CSV (Cloud Run)
    ├── ml/elasticity.py log-log OLS → elasticity + profit curve
    ├── agents/graph.py  LangGraph: Analyst → Strategist → Reviewer
    ├── guardrails.py    price-safety + number-grounding checks
    └── cache.py         Redis result cache (optional, degrades to no-op)
postgres  seeded once from data/dataset.csv
redis     caches ML/agent results (agent runs cost API tokens)
```

Key design decision: the data layer is a two-method Protocol
(`list_products`, `product_series`) with a Postgres and a CSV
implementation. Docker compose runs the full stack; a single stateless
container (e.g. Cloud Run) runs the same code from the bundled CSV.

## The ML model

`backend/app/ml/elasticity.py` — deliberately simple, fast enough to run
per request, and explainable to a business stakeholder:

1. **Aggregate daily → weekly.** 36% of daily rows have zero sales; weekly
   totals smooth that noise into ~104 clean observations per product/market.
2. **Log-log OLS:** `ln(units) = a + e·ln(price) + b·ln(ad_spend+1) + month dummies`.
   The price coefficient `e` **is** the price elasticity. Ad spend and month
   dummies absorb promotion/seasonality effects (Black Friday weeks have low
   prices *and* high ads — without the controls the elasticity would be biased).
3. **Optimal price:** predict weekly demand on a 50-point price grid strictly
   inside the observed price range (no extrapolation), pick the price that
   maximises `(price − cost) × predicted units`.

The API returns elasticity, R², the full profit curve, a confidence label,
and explicit warnings (inelastic demand, edge-of-range optimum, low fit).

## The AI agents

`backend/app/agents/graph.py` — a **deterministic, linear LangGraph**:

```
Analyst  →  Strategist  →  Reviewer
```

| Agent | Role | Output schema |
|---|---|---|
| Data Analyst | translates the ML result into plain business language | `AnalystFindings` |
| Pricing Strategist | recommends one price, sanity-checked against cost/current price | `StrategistRecommendation` |
| Risk Reviewer | verdict `approve/revise/reject` with explicit checks | `ReviewerVerdict` |

Design choices, in line with "complexity does not mean better":

- **Linear graph, no LLM routing** — there is no branching decision an LLM
  should make here; determinism keeps latency, cost and audit trails predictable.
- **Structured output everywhere** (`with_structured_output` + Pydantic) — no
  free-text parsing.
- **Compact numeric payload** (~16 fields, no raw rows) — 3 calls of a few
  hundred tokens each per analysis; results cached in Redis for 24 h.
- **Code-level guardrail after the agents** (`guardrails.py`): the recommended
  price must clear cost + 2%, stay within ±30% of the current price and near
  the observed price range. Violations are shown as a red banner in the UI —
  the LLM reviewer is a second opinion, not the only safety net.
- Prompts live in `agents/prompts.py`; every prompt forbids inventing numbers.

## AI output evaluation (lightweight)

```bash
cd backend
DATASET_PATH=../data/dataset.csv python -m scripts.evaluate_agents               # 3 example cases
DATASET_PATH=../data/dataset.csv python -m scripts.evaluate_agents --inject-bad  # prove the checks catch bad output
```

Four checks per case: **structure** (schema conformance), **grounding**
(every number an agent cites appears in its input payload, ±5%),
**safety** (above cost, plausible move, inside observed range), and
**consistency** (the reviewer must not approve a recommendation that fails
guardrails). With an `OPENAI_API_KEY` set it evaluates live LLM output;
without one it runs against simulated output so the checks themselves are
always testable (that offline mode also runs in CI). `--inject-bad`
demonstrates detection: an invented competitor price and a below-cost
recommendation are flagged by 3 of the 4 checks.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest tests -v
```

26 tests: schema validation, all guardrails, ML sanity (the model recovers a
known elasticity of −2.0 from synthetic data), the agent graph with a fake
LLM, and API integration tests. CI (`.github/workflows/ci.yml`) runs lint,
tests, the offline agent evaluation, and the frontend type-check/build on
every push.

## Deployment (Google Cloud Run)

`.github/workflows/deploy.yml` builds both images with Cloud Build and
deploys two Cloud Run services (backend in CSV mode — no managed DB needed
for the PoC). Configure repo variables `GCP_PROJECT_ID`, `GCP_REGION` and
secrets `GCP_SA_KEY`, `OPENAI_API_KEY`, create the Artifact Registry repo
once (command in the workflow header), and push to `main`.

## Configuration

All configuration is environment-based (`pydantic-settings`); see
`.env.example`. No secrets or URLs are hardcoded. `/health` returns
`200 OK` for container health checks. Logs are structured JSON (structlog);
every agent run logs model, input hash, latency and guardrail status.

## Limitations (honest ones)

- **Observational elasticity, not causal.** Prices weren't randomized; the
  controls (ad spend, month) reduce but don't eliminate confounding. A/B
  price tests would be the next step before trusting the numbers operationally.
- **Constant-elasticity assumption.** One log-log slope per product/market;
  no cross-product cannibalisation, no competitor prices (not in the data).
- **No extrapolation beyond observed prices** — a safety feature, but it means
  the "optimal" price can sit at the range edge (the app flags this).
- **`web_sessions` is unused** in the model: sessions are partly a *consequence*
  of price (via ad-driven promo traffic), so including them would soak up part
  of the price effect (mediator bias).
- **Missing `ad_spend` (~15% of rows) is treated as zero** — reasonable for
  paid-marketing data, but unverified.
- **Agent output is advisory.** Guardrails check plausibility, not truth; the
  human-in-the-loop is the category manager reading the dashboard.
- Redis caches by product/market/model only — fine here because the dataset is
  static; a live system would include a data-version in the key.
