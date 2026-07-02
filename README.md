# MindBridge — Student Mental Wellness Tracker

A two-tier web application for daily self-reported wellness check-ins, built for the **INCO (Innovation and Complexity Management)** course requirements.

## INCO compliance highlights

| Requirement | Implementation |
|---|---|
| Two-tier architecture | React frontend + Python HTTP API + SQLite |
| FHIR-compliant JSON | `GET /api/fhir/Bundle`, `GET /api/fhir/Patient`; logs return FHIR Observations on save |
| d3.js visualization | Interactive mood/stress line chart and sleep/energy bar chart in `AnalyticsCharts.js` |
| Real-time updates | Server-Sent Events at `GET /api/events` — charts refresh when a check-in is saved |
| JWT authentication | Bearer tokens on all protected `/api/*` routes |
| Input validation | Server-side range/schema checks in `server/validation.py` |
| Structured logging | Python `logging` with timestamps in `run.py` |
| Testing | `pytest` unit + integration tests in `tests/` |
| CI/CD | GitHub Actions workflow in `.github/workflows/ci.yml` |
| Containerized deployment | `Dockerfile` + `docker-compose.yml` |

Evaluation reference: [INCO Development Checklist](https://dominikboehler.de/inco_new/#development-checklist--evaluation-criteria)

## Features

- Secure login & signup (hashed passwords + JWT)
- Onboarding wizard for student preferences
- Daily wellness check-in (mood, energy, sleep, stress)
- d3.js analytics charts with real-time SSE updates
- FHIR R4 Observation bundles for interoperability
- Resource hub with campus support links
- Dark / light mode

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React (CDN), d3.js, Tailwind CSS |
| Backend | Python `http.server` (stdlib) |
| Database | SQLite3 |
| Auth | HMAC-SHA256 JWT (stdlib) |
| Real-time | Server-Sent Events (SSE) |

## Getting started

### Prerequisites
- Python 3.11+
- Docker (optional, recommended)

### Run locally

```bash
python run.py
```

Open **http://localhost:8000**

### Run with Docker

```bash
docker compose up --build
```

### Run tests

```bash
pip install -r requirements-dev.txt
python -m pytest --cov=server --cov-report=term-missing tests/ -v
```

## Configuration

Copy an environment template from `config/`:

- `config/dev.env.example` — local development
- `config/prod.env.example` — production (set `JWT_SECRET` and `CORS_ORIGIN`)

| Variable | Description |
|---|---|
| `MINDBRIDGE_ENV` | `dev`, `stage`, or `prod` |
| `JWT_SECRET` | Signing key for bearer tokens |
| `DB_PATH` | SQLite database file path |
| `PORT` | HTTP server port (default 8000) |
| `CORS_ORIGIN` | Allowed origin in production |

## API endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/create-profile` | No | Sign up |
| POST | `/api/session` | No | Log in (returns JWT) |
| GET | `/api/logs` | Bearer | List wellness logs |
| POST | `/api/logs` | Bearer | Save daily check-in (+ FHIR payload) |
| GET | `/api/fhir/Bundle` | Bearer | FHIR Bundle of Observations |
| GET | `/api/fhir/Patient` | Bearer | FHIR Patient resource |
| GET | `/api/events` | Bearer | SSE real-time stream |
| GET | `/api/health` | No | Health check |

## Project structure

```
mindbridge/
├── run.py                  # HTTP server + API routes
├── server/
│   ├── auth.py             # JWT create/verify
│   ├── fhir.py             # FHIR R4 mapping
│   ├── validation.py       # Input validation
│   ├── events.py           # SSE pub/sub
│   └── config.py           # Environment config
├── tests/
│   └── test_api.py         # Unit + integration tests
├── config/                 # Environment templates
├── .github/workflows/ci.yml
└── src/
    ├── App.js
    ├── AnalyticsCharts.js  # d3.js charts
    ├── CheckInForm.js
    ├── db.js               # API client + SSE
    └── ...
```

## How users enter data

Students open the **website** in a browser and complete a short **daily survey**:

- **Mood** — 5 emoji buttons (1–5)
- **Energy** — 5 levels (1–5)
- **Stress** — slider (1 = calm, 5 = burnout)
- **Sleep** — hours slider + quality (Poor/Fair/Good)
- **Notes & tags** — optional free text

Data is self-reported (not from phone sensors or wearables).
