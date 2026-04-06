# aircraft-health-cag-demo

A portfolio project demonstrating Cognite Data Fusion (CDF)
architecture and Context Augmented Generation (CAG) at small
scale, using a fleet of aircraft as the subject domain.

**Operator:** Desert Sky Aviation — flight school, KPHX  
**Fleet:** Four 1978 Cessna 172N Skyhawks (N4798E, N2251K, N8834Q, N1156P)  
**Engine:** Lycoming O-320-H2AD (shared across fleet — enables cross-aircraft pattern discovery)  
**Stack:** Python (FastAPI) backend + React TypeScript frontend

Application code and tooling live in [`aircraft-health-cag-demo/`](aircraft-health-cag-demo/). All commands below assume you have changed into that directory first.

---

## Quick Start

```bash
cd aircraft-health-cag-demo
```

**Prerequisites:** Node.js 18+ and Python 3.9+ (`python3` on your PATH). A virtualenv is recommended:

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

**One-time setup** (installs npm deps, installs Python package editable, generates CSVs, runs ingestion):

```bash
npm run bootstrap
```

**Configure the agent** — copy the example env file and add your key:

```bash
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY=sk-ant-...
```

**Run the stack** (mock CDF, API, Vite):

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

| Service | Port | Description |
|---------|------|-------------|
| Mock CDF Server | 4000 | FastAPI implementing CDF REST API |
| API Server | 3000 | FastAPI exposing agent to frontend |
| Vite Dev Server | 5173 | React frontend (proxies /api → 3000) |

---

## What This Demonstrates

### The IT/OT/ET Convergence Problem

Cognite Data Fusion solves a fundamental industrial challenge:
operational data lives in three disconnected worlds that were
never designed to talk to each other.

| Data Type | Industrial (CDF) | Aviation (This Project) |
|-----------|-----------------|------------------------|
| **OT** Operational Technology | Sensor data from PLCs/SCADA | Flight instrument readings (CHT, EGT, oil pressure, hobbs) |
| **IT** Information Technology | Work orders in SAP/ERP | Maintenance logbook, squawks, annual inspections |
| **ET** Engineering Technology | CAD models, P&IDs, equipment specs | POH sections, FAA Airworthiness Directives, Service Bulletins |

This project ingests all three layers into a unified knowledge
graph and runs an AI agent over the connected data.

### CDF Resource Types

| CDF Resource | This Project |
|-------------|-------------|
| **Asset** | Fleet hierarchy: Desert_Sky_Aviation → N4798E → ENGINE → ENGINE-CYLINDERS |
| **TimeSeries** | Sensor streams per aircraft: `N4798E.engine.cht_max`, `N8834Q.aircraft.hobbs` |
| **Datapoints** | Instrument readings per flight (OT layer) |
| **Events** | Maintenance records, squawks, inspections, flight events (IT layer) |
| **Relationships** | HAS_COMPONENT, IS_TYPE, EXHIBITED, GOVERNED_BY, HAS_POLICY, PERFORMED_ON, REFERENCES_AD |
| **Files** | POH sections, ADs, Service Bulletins (ET layer) |

### Swapping Mock for Real CDF

Two lines in `.env` inside `aircraft-health-cag-demo/` (after `cd aircraft-health-cag-demo`):

```bash
# Mock (current)
CDF_BASE_URL=http://localhost:4000
CDF_TOKEN=mock-token

# Real CDF tenant
CDF_BASE_URL=https://api.cognitedata.com
CDF_TOKEN=<your-oidc-token>
```

Zero code changes. The `cognite-sdk` Python client is
identical against both.

---

## CAG vs RAG

### Standard RAG
```
Question → Embedding → Vector similarity search →
Top-K text chunks → LLM answer
```
Loses structure. Loses relationships. Cannot traverse
connected data. Cannot cross-reference assets.

### CAG — Cognite's Approach
```
Question → Agent traverses knowledge graph →
Aircraft → Components → Events → Relationships →
Documents → Connected context → LLM answer
```

**Every node visited is logged.** The UI shows exactly
which graph nodes informed the answer in real time.

This project uses no vector store and no embeddings.
Context comes entirely from graph traversal.

---

## Cross-Aircraft Pattern Discovery

The most powerful CAG capability in this demo: the agent
can identify that N8834Q's current symptoms match the
pattern that preceded N1156P's catastrophic engine failure
— without any hardcoded causal relationships in the graph.

**How it works:**

```
N8834Q-ENGINE → IS_TYPE → ENGINE_MODEL_LYC_O320_H2AD
N1156P-ENGINE → IS_TYPE → ENGINE_MODEL_LYC_O320_H2AD
```

When investigating N8834Q's symptoms, the agent calls
`get_engine_type_history()` which traverses IS_TYPE to
find all aircraft sharing the same engine model, then
reads their time-ordered events chronologically. It
discovers N1156P's deteriorating pattern through temporal
reasoning over connected data — not through hardcoded
cause-effect edges.

This mirrors exactly how Cognite Atlas AI reasons across
industrial assets: find similar equipment via asset class
relationships, compare operational histories, surface
relevant patterns.

---

## Fleet Status

| Aircraft | Status | Story |
|----------|--------|-------|
| N4798E | AIRWORTHY ✓ | Clean reference aircraft. Oil change due in 18 hours. |
| N2251K | FERRY ONLY ⚠ | Oil change 1 hour overdue. Ferry to maintenance permitted per fleet policy. |
| N8834Q | CAUTION ⚠ | Last 3 flights show progressive CHT #3 elevation and rough mag check. Matches pre-failure pattern from N1156P. |
| N1156P | GROUNDED ✗ | Catastrophic engine failure 6 months ago. Piston failure from blocked injector. Engine condemned. |

---

## Fleet Operational Policies

Policies are stored as nodes in the knowledge graph
(not hardcoded in application logic) and retrieved by
the agent at query time. This mirrors how Cognite
customers store operational thresholds alongside
asset data.

- **OIL_CHANGE_GRACE** — ferry flight permitted if overdue ≤5 hours
- **ANNUAL_GRACE** — no grace period, FAR 91.409
- **SYMPTOM_ESCALATION** — CHT deviation >20°F on two consecutive flights or mag drop >50 RPM requires A&P inspection before next flight (established after N1156P incident)
- **OIL_ANALYSIS** — every third oil change or annually

Try: *"Have all aircraft been maintained to the owner's specifications?"*

---

## Project Structure

From the repository root:

```
.
└── aircraft-health-cag-demo/
    ├── package.json              ← single npm manifest (client deps hoisted)
    ├── pyproject.toml            ← Python dependencies (pip install -e .)
    ├── .env.example
    ├── data/
    │   ├── flight_data_{TAIL}.csv        ← OT: flights per aircraft
    │   ├── maintenance_{TAIL}.csv        ← IT: maintenance per aircraft
    │   └── documents/                    ← ET: POH, ADs, SBs
    ├── mock_cdf/
    │   ├── server.py                 ← FastAPI mock CDF (port 4000)
    │   ├── store/store.py            ← Pydantic models + JSON persistence
    │   └── routes/                   ← assets, timeseries, events,
    │                                    relationships, files, symptoms, policies
    ├── src/
    │   ├── agent/
    │   │   ├── tools.py              ← CDF query tools + fleet tools
    │   │   ├── context.py            ← assemble_aircraft_context + fleet
    │   │   └── agent.py              ← Claude ReAct loop → SSE
    │   ├── ingest/
    │   │   ├── ingest_assets.py      ← 4 aircraft + ENGINE_MODEL node
    │   │   ├── ingest_flights.py     ← per-tail TimeSeries + Datapoints
    │   │   ├── ingest_maintenance.py
    │   │   └── ingest_fleet_graph.py ← symptoms, policies, IS_TYPE, etc.
    │   └── api.py                    ← FastAPI API server (port 3000)
    ├── scripts/
    │   ├── dataset.py                ← single source of truth
    │   ├── transform_flights_to_cag.py
    │   └── transform_maintenance_to_cag.py
    └── client/
        └── src/
            ├── components/
            │   ├── FleetOverview.tsx      ← 2×2 aircraft status grid
            │   ├── QueryInterface.tsx     ← Chat + SSE streaming
            │   ├── GraphTraversalPanel.tsx← Real-time node list (150ms stagger)
            │   ├── KnowledgeGraph.tsx     ← Force-directed fleet graph
            │   ├── MaintenanceTimeline.tsx← Per-aircraft history
            │   ├── FlightHistory.tsx      ← Per-aircraft flights
            │   └── AircraftComponents.tsx ← Component hierarchy
            └── lib/
                ├── store.ts              ← Zustand (selectedAircraft, chat,
                │                            traversal)
                ├── types.ts
                └── api.ts
```

---

## Sample Queries

**Fleet-wide:**
```
"Which aircraft needs attention most urgently?"
"Have all aircraft been maintained to the owner's specifications?"
"Are any aircraft showing symptoms similar to what preceded the N1156P failure?"
"What is the fleet maintenance status?"
```

**N8834Q (the important one):**
```
"Should I be concerned about N8834Q's recent flights?"
"What do N8834Q's symptoms historically indicate in this fleet?"
```

**N1156P:**
```
"What caused the N1156P engine failure?"
"What were the warning signs before N1156P failed?"
```

**N4798E:**
```
"Is N4798E airworthy for today's flight?"
"Has this aircraft complied with all applicable ADs?"
"What does the POH say about engine oil pressure limits?"
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/query` | SSE-streamed agent response |
| GET | `/api/health` | Service status + graph node counts |
| GET | `/api/fleet` | All four aircraft with status |
| GET | `/api/status?aircraft={tail}` | Single aircraft health data |
| GET | `/api/squawks?aircraft={tail}` | Open squawks |
| GET | `/api/maintenance/history?aircraft={tail}` | Maintenance records |
| GET | `/api/flights?aircraft={tail}` | Flight history |
| GET | `/api/components?aircraft={tail}` | Component hierarchy |
| GET | `/api/graph` | Full fleet knowledge graph |
| GET | `/api/policies` | Fleet operational policies |

---

## Aviation → Industrial Use Case Map

| Aviation Query | Industrial Equivalent |
|---------------|----------------------|
| "Is N4798E safe to fly?" | "Is this equipment safe to operate?" |
| "What symptoms preceded the N1156P failure?" | "What sensor patterns preceded this pump failure?" |
| "Which aircraft has the same engine type?" | "Which assets share this equipment class?" |
| "Have all aircraft met the oil change policy?" | "Have all assets met the maintenance schedule?" |
| "What does AD 80-04-03 R2 require?" | "What does this compliance standard require?" |
| CHT elevation across multiple flights | Bearing temperature trend across multiple cycles |

The same graph traversal that connects N8834Q's symptoms
to N1156P's failure history connects a compressor's
vibration readings to a similar compressor's failure
record — the architecture is identical.
