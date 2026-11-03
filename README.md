# dengar-ai
# DengarAI — FastAPI Data Processing & Analytics Pipeline

A Python/FastAPI backend for processing DengarAI conversation datasets, enriching them with language and sentiment/topic analysis, applying AI-assisted scoring, preparing session-level analytical data, and generating HTML dashboards.

> **Project status:** The API has been deployed to Render at [https://dengar-ai.onrender.com](https://dengar-ai.onrender.com). Successful execution of the **complete** processing workflow on Render, including model loading, scoring, and persistent output storage, must be verified separately from web-service deployment.

## API links

| Resource | URL |
|---|---|
| Base URL | `https://dengar-ai.onrender.com` |
| OpenAPI / Swagger UI | [https://dengar-ai.onrender.com/docs](https://dengar-ai.onrender.com/docs) |
| Health check | [https://dengar-ai.onrender.com/health](https://dengar-ai.onrender.com/health) |
| OpenAPI schema | [https://dengar-ai.onrender.com/openapi.json](https://dengar-ai.onrender.com/openapi.json) |

The URLs above represent the intended FastAPI routes. Check them against the live deployment. A `404` at `/` means there is no root endpoint; it does not on its own indicate failure of `/docs` or the API.

## What the project does

The processing pipeline is organized into five stages:

| Stage | Script | Purpose | Typical output |
|---|---|---|---|
| 1 — Data cleaning | `scripts/data_cleaning.py` | Validates, cleans, and structures uploaded conversation CSVs | Separate `[cleaned].csv` files per dataset |
| 2 — Sentiment and topic analysis | `scripts/sentiment_topic.py` | Enriches conversation/session data with sentiment, topics and related classifications | Updated cleaned CSVs and `session_summary.csv` |
| 3 — AI scoring | `scripts/ai_scoring.py` | Produces structured AI-assisted assessments using an external API | Updated cleaned CSVs and scoring `.jsonl` files |
| 4 — Analyzation | `scripts/analyzation.py` | Combines processed information into analytics-ready session records | `analyzed.csv` |
| 5 — Dashboard generation | `scripts/dashboard_v9.py` | Produces HTML dashboards from analyzed results | `dashboard_v9.html` and linked dashboard pages |

### Workflow

```text
Upload at least two conversation CSVs (e.g., SP1 + SP9)
    |
    v
FastAPI job creation -> job_id
    |
    v
01 Data cleaning -> cleaned CSVs
    |
    v
02 Sentiment / topic analysis -> updated CSVs + session summary
    |
    v
03 AI scoring -> enriched CSVs + scoring JSONL
    |
    v
04 Analyzation -> analyzed.csv
    |
    v
05 Dashboard generation -> HTML dashboard files
    |
    v
Job status + output downloads through FastAPI
```

AI scoring may be billed by its API provider. Use non-sensitive test datasets and control scoring volume during development.

## Repository layout

The repository may contain the following files (adjust to match the checked-in project):

```text
dengarai_pipeline_fastapi/
├── main.py
├── requirements.txt
├── README.md
├── scripts/
│   ├── data_cleaning.py
│   ├── sentiment_topic.py
│   ├── ai_scoring.py
│   ├── analyzation.py
│   ├── dashboard_v9.py
│   ├── executive.py
│   ├── operations.py
│   ├── user_behavior.py
│   ├── citizen_voice.py
│   └── citizen_issue_intelligence.py
└── data/
    └── jobs/                   # Runtime job data (do not commit confidential files)
```

Additional modules, configuration files and assets imported by the scripts must be included in the repository.

## Run locally (Windows / PowerShell)

Requirements: Python (use the version supported by `requirements.txt`; Python 3.11 is a starting point), pip, and access to any required model downloads.

```powershell
# From the repository root
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Start the local API
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

Open:
- Swagger UI: `http://127.0.0.1:8001/docs`
- Health check: `http://127.0.0.1:8001/health`

Use environment variables or a secret manager for API credentials. For example, `OPENAI_API_KEY` must be set **only if the scoring implementation requires it**. Never hardcode or commit a real API key.

## HTTP API

The endpoint descriptions below reflect the project's documented local workflow. **Always consult the generated Swagger/OpenAPI schema for exact request fields, upload field names, response bodies and supported job parameters.**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Check service health |
| `POST` | `/api/jobs/upload` | Upload datasets and create a job |
| `POST` | `/api/jobs/{job_id}/run` | Start the pipeline for an uploaded job |
| `GET` | `/api/jobs/{job_id}` | Query job status |
| `GET` | `/api/jobs/{job_id}/log` | Read processing logs |
| `GET` | `/api/jobs/{job_id}/files` | List generated files |
| `GET` | `/api/jobs/{job_id}/files/{file_path}` | Retrieve an output file |
| `GET` | `/api/jobs/{job_id}/dashboard` | Open generated dashboard, when available |

### Typical frontend integration

1. Upload **at least two** raw CSV datasets using the request format shown in Swagger.
2. Save the `job_id` returned by `/api/jobs/upload`.
3. Send `POST /api/jobs/{job_id}/run`.
4. Poll `GET /api/jobs/{job_id}` to display progress; use the log endpoint for troubleshooting.
5. After successful completion, list/download outputs or open the dashboard endpoint.

Example health check from a JavaScript frontend:

```javascript
const API_BASE_URL = "https://dengar-ai.onrender.com";

async function checkHealth() {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) throw new Error(`Health check failed: ${response.status}`);
  return response.json();
}
```

For browser-based frontends on another domain, configure FastAPI CORS to allow **only the intended frontend origins**. File uploads should use `FormData` with the exact field names defined by `/docs`.

## Render deployment

The existing Render service uses the public base URL above. For a Python web service, the usual configuration is:

**Build command**

```bash
pip install -r requirements.txt
```

**Start command**

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set required secrets through Render's environment-variable settings, not GitHub. Ensure the selected instance has enough RAM, CPU, disk space and startup time for transformer models and topic modeling. Verify the complete workflow with a small **non-sensitive** test dataset before accepting production traffic.

### Important production limitations

- **Persistence:** Cloud web-service filesystems may be ephemeral. Store job state and generated files on persistent storage (such as a configured disk, object storage or database) rather than assuming `data/jobs/` survives restarts or redeployments.
- **Background processing:** Heavy sentiment/topic modeling and AI-scoring jobs should use a reliable worker/queue with restart-safe checkpoints. A running Uvicorn process alone is not durable job execution.
- **Security:** Add authentication, authorization, upload limits and safe file-path validation before exposing citizen transcripts, scored datasets or job outputs to the public internet.
- **Privacy:** Confirm hosting region, retention, access policies and any relevant organizational requirements before processing real DengarAI conversation data.
- **Operational cost:** Large ML models need suitable compute resources; external AI scoring incurs API charges.
- **CORS and HTTPS:** Permit the intended frontend origin(s) and use HTTPS for public API access.

## Debugging HTTP 404 responses

If the Render logs show:

```text
GET / HTTP/1.1          404 Not Found
GET /favicon.ico        404 Not Found
```

this can be normal: FastAPI does not automatically define a homepage or favicon. Test `/health` and `/docs` to check API availability. An optional root endpoint can be added to `main.py`:

```python
@app.get("/")
def home():
    return {"service": "DengarAI FastAPI", "docs": "/docs", "health": "/health"}
```

Add this **only after** the existing FastAPI `app` instance is created, and avoid duplicate `GET /` routes.

## Handoff checklist

- [ ] Live `/health` and `/docs` verified
- [ ] Exact Swagger request/response schema reviewed with frontend developer
- [ ] Credentials removed from repository and history
- [ ] Non-sensitive test CSVs available
- [ ] At least one complete cloud processing job tested
- [ ] Generated CSV/JSONL/HTML files persist across restart
- [ ] CORS and access controls configured for the frontend
- [ ] AI-scoring usage and error recovery tested

---

**Development note:** This README describes the planned and locally tested DengarAI pipeline; deployment of the web server alone does not prove that every data-processing stage has completed successfully in the hosted environment.
