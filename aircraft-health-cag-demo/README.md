# N4798E Aircraft Health Assistant — CAG Demo

A portfolio project demonstrating Cognite Data Fusion (CDF) architecture and Context Augmented Generation (CAG) at small scale, using a real aircraft as the subject domain.

**Subject:** 1978 Cessna 172N Skyhawk, N4798E — Lycoming O-320-H2AD, ~4,800 hrs TT, based at KPHX

**Stack:** Python (FastAPI) backend + React TypeScript frontend

---

## Quick Start

```bash
# Install dependencies
npm install              # root — installs concurrently
cd client && npm install # React frontend deps
cd ../backend && pip install -r requirements.txt

# Generate sample data
npm run generate

# Ingest data into the knowledge graph
npm run ingest

# Add your Anthropic API key
echo "ANTHROPIC_API_KEY=sk-ant-..." >> backend/.env

# Start everything
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

Three services start:
| Service | Port | Description |
|---------|------|-------------|
| Mock CDF Server | 4000 | FastAPI implementing CDF REST API |
| API Server | 3000 | FastAPI exposing agent to frontend |
| Vite Dev Server | 5173 | React frontend (proxies /api → 3000) |

---

## What This Demonstrates

### Cognite Data Fusion Architecture

Cognite Data Fusion (CDF) solves the **IT/OT/ET convergence problem** in industrial operations — ingesting data from three distinct source systems into a unified knowledge graph:

| Data Type | Industrial (CDF) | Aviation (This Project) |
|-----------|------------------|------------------------|
| **OT** — Operational Technology | Sensor data from PLCs/SCADA | Flight instrument readings (CHT, EGT, oil pressure, hobbs time) |
| **IT** — Information Technology | Work orders in SAP/ERP | Maintenance logbook records, squawks, annual inspections |
| **ET** — Engineering Technology | CAD models, P&IDs, equipment specs | POH sections, FAA Airworthiness Directives, Lycoming Service Bulletins |

### CDF Resource Types → Knowledge Graph Nodes

| CDF Resource | This Project |
|-------------|-------------|
| **Asset** | Aircraft component hierarchy: N4798E → ENGINE-1 → ENGINE-1-CAM-LIFTERS |
| **TimeSeries** | Sensor streams: `aircraft.hobbs`, `engine.cht_max`, `engine.oil_pressure_max` |
| **Datapoints** | Actual instrument readings per flight (OT layer) |
| **Events** | Maintenance records, squawks, annual inspections (IT layer) |
| **Relationships** | PERFORMED_ON, REFERENCES_AD, RESOLVED_BY, LINKED_TO edges |
| **Files** | POH sections, ADs, Service Bulletins (ET layer) |

### How to Swap the Mock for Real CDF

Only two lines change in `backend/.env`:

```bash
# Mock (current)
CDF_BASE_URL=http://localhost:4000
CDF_TOKEN=mock-token

# Real CDF tenant
CDF_BASE_URL=https://api.cognitedata.com
CDF_TOKEN=<your-oidc-token>
```

Zero code changes required. The `cognite-sdk` Python client works identically against both.

---

## CAG vs RAG — Why This Matters

### Standard RAG (Retrieval Augmented Generation)
```
Question → Embedding → Vector similarity search → Top-K chunks → LLM
```
Problems: loses structure, loses relationships, can hallucinate on structured data, no traceable reasoning.

### CAG (Context Augmented Generation) — Cognite's Approach
```
Question → Agent identifies relevant graph nodes → 
  Traverse: Aircraft → Components → Events → Relationships → Documents →
  Assemble connected context → LLM
```

Advantages:
- **Traceable:** Every graph node visited is logged — the UI shows exactly which nodes informed the answer
- **Structured:** Maintenance records, AD references, sensor values maintain their relational structure
- **Accurate:** No hallucination on structured data — hobbs times, AD numbers, dates are read directly from the graph
- **Connected:** A single query can traverse IT (maintenance) → ET (AD document) → OT (sensor readings) naturally

This is implemented in `backend/src/agent/context.py` (`assemble_aircraft_context()`) and `backend/src/agent/tools.py`.

---

## Project Structure

```
aircraft-health-cag-demo/
├── data/                          ← IT/OT/ET source data
│   ├── flight_data.csv            ← OT: 300+ flights from KPHX
│   ├── maintenance_log.csv        ← IT: full history 1978–2026
│   └── documents/                 ← ET: POH, ADs, SBs
├── backend/
│   ├── mock_cdf/                  ← FastAPI mock CDF server (port 4000)
│   │   ├── server.py
│   │   ├── store/store.py         ← Pydantic models + JSON persistence
│   │   └── routes/                ← assets, timeseries, events, relationships, files
│   ├── src/
│   │   ├── agent/
│   │   │   ├── tools.py           ← 9 CDF query tools via cognite-sdk
│   │   │   ├── context.py         ← assembleAircraftContext() — CAG core
│   │   │   └── agent.py           ← Claude ReAct loop (async generator → SSE)
│   │   ├── ingest/                ← 4-stage ingestion pipeline
│   │   └── api.py                 ← FastAPI application API (port 3000)
│   └── scripts/
│       ├── generate_flight_data.py
│       └── generate_maintenance_log.py
├── client/                        ← Vite + React + TypeScript
│   └── src/
│       ├── components/
│       │   ├── StatusDashboard.tsx     ← Aircraft health cards
│       │   ├── QueryInterface.tsx      ← Chat + SSE streaming
│       │   ├── GraphTraversalPanel.tsx ← Real-time node visualization
│       │   └── MaintenanceTimeline.tsx ← Upcoming + history
│       └── lib/
│           ├── types.ts               ← TypeScript interfaces
│           ├── api.ts                 ← Backend API calls
│           └── utils.ts
└── package.json                   ← Orchestration (concurrently)
```

---

## The Aircraft: N4798E

This is a real FAA-registered aircraft. The O-320-H2AD engine makes it an interesting maintenance subject:

- **The H2AD cam/lifter problem:** Lycoming used barrel-shaped hydraulic lifters (vs. standard mushroom-type) to allow servicing without splitting the crankcase. The design caused cam lobe spalling under higher loads. **AD 80-04-03 R2** mandates recurring inspection at defined intervals. The elevated iron in the last oil analysis (22 ppm) is consistent with this known wear pattern.

- **Applicable ADs:** 80-04-03 R2 (cam/lifters), 90-06-03 R1 (exhaust muffler), 2001-23-03 (door post wiring), 2011-10-09 (seat rail)

- **Current status:** SMOH ~1450 hrs of 2000 hr TBO, annual due June 2026, 3 open non-grounding squawks

---

## Aviation → Industrial Use Case Map

| "Is N4798E safe to fly?" | "Is equipment safe to operate?" |
|--------------------------|----------------------------------|
| Annual inspection currency | Regulatory/safety certification |
| AD compliance tracking | Compliance monitoring |
| Component maintenance history | Asset lifecycle management |
| Sensor anomaly detection (CHT, EGT) | Equipment health monitoring |
| Squawk tracking | Work order / issue management |
| POH limitations | Equipment specifications |

The same CAG architecture that answers "What does the cam/lifter AD require?" answers "What does the safety standard require for this compressor?" — the graph traversal is identical.

---

## Sample Questions

```
"Is N4798E currently airworthy?"
"What maintenance is coming due in the next 50 hours?"
"When was the last oil change and when is the next one due?"
"What does the POH say about engine oil pressure limits?"
"Are there any open squawks?"
"Give me a full health summary of N4798E"
"Has this aircraft complied with all applicable ADs?"
"What are the emergency procedures for engine failure?"
"Tell me about the history of engine maintenance on this aircraft"
"What's the status of the cam and lifter inspections?"
"When is the next transponder inspection due?"
"What major work has been done on the airframe?"
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/query` | SSE-streamed agent response |
| GET | `/api/health` | API key + mock CDF status |
| GET | `/api/status` | Aircraft health dashboard data |
| GET | `/api/squawks` | Open squawks |
| GET | `/api/maintenance/upcoming` | Due in next 100 hobbs |
| GET | `/api/maintenance/history` | Recent maintenance records |
