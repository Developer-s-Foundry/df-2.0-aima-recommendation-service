# AIMAS Recommendation Service

A microservice in the **AIMAS** (Ai-based Incident Management & Alert System) stack that **consumes metrics** (via RabbitMQ), applies **deterministic rules** and/or **LLM analysis**, and **publishes recommendations** back to RabbitMQ. It also exposes a small **HTTP API** for health checks and to **query recommendations**.

> 🔧 If you need a step-by-step guide to install **Prometheus**, **Windows Exporter**, **Erlang** and **RabbitMQ** on Windows, see:
> `Prometheus_windows_setup.md` (in this repo)

---

## What this service does

* Subscribes to log/metric events from RabbitMQ (e.g., `system.cpu`, `system.memory`, `system.disk`, `system.net`, etc.).
* Generates recommendations using:

  * **Rules engine** (always available), and
  * **LLM** (optional, if `OPENAI_API_KEY` is set).
* Publishes results to the **`recommendations`** exchange (topic).
* Persists recommendations to **SQLite** (for `/recommendations` API).
* Exposes health endpoints and a REST API.

---

## Project Structure

```
df-2.0-aima-recommendation-service/
├─ app.py                     # FastAPI app: /health/* and /recommendations endpoints
├─ consumer.py                # Hybrid consumer (rules + optional LLM) + publisher to recommendations
├─ rules/
│  ├─ base.py
│  ├─ cpu_rules.py
│  ├─ memory_rules.py
│  ├─ disk_rules.py
│  ├─ system_net_rules.py
│  ├─ network_http_rules.py
│  └─ error_rate_rules.py
├─ storage.py                 # SQLite persistence for recommendations
├─ rabbitmq_publisher.py      # Utility publisher for recommendations
├─ .env            # Sample env file (copy to .env)
├─ requirements.txt
└─ Prometheus_windows_setup.md   # Windows setup guide for Prometheus & RabbitMQ
```

---

## Quick Start (Local, no Docker)

### 1) Clone the repo

```bash
git clone hhttps://github.com/Developer-s-Foundry/df-2.0-aima-recommendation-service.git
cd df-2.0-aima-recommendation-service
```

### 2) Create & activate a virtual environment

```bash
# Windows (PowerShell)
python -m venv .venv
. .\.venv\Scripts\Activate.ps1

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Configure environment

Edit the .env and add your own OpenAI key

**Important variables (edit in `.env`):**

```env
# Optional LLM
OPENAI_API_KEY=

```

> ℹ️ If you don’t have a central RabbitMQ yet, install one locally (see the Windows guide in `Prometheus_win_exporter_rabbitmq.md`) or use a remote URL in `RABBIT_URL`.

### 5) Run the API (health + recommendations)

```bash
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
``` 

- **Liveness:** `GET http://localhost:8080/health/live`
- **Readiness:** `GET http://localhost:8080/health/ready`
- **Recommendations:** `GET http://localhost:8080/recommendations`
- **Recommendations/Analyze:** `POST http://localhost:8080/recommendations/analyze`

### 6) Run the Recommendation Consumer

In a second terminal:

```bash
python consumer.py
```

* This listens to `RABBIT_LOG_EXCHANGE=logs` with binding keys from `RABBIT_LOG_BINDINGS`.
* It publishes to `RABBIT_RECO_EXCHANGE=recommendations`.

---

## 🌐 REST API

### 1) `GET /health/ready`

**Auth:** Not required
**Purpose:** Dependency health (RabbitMQ, DB, etc.)

**200 OK**

```json
{ "status": "ready", "version": "0.1.0" }
```

**503 Service Unavailable**

```json
{ "status": "not ready", "error": "Cannot connect to RabbitMQ" }
```

---

### 2) `GET /recommendations`

**Purpose:** Return stored recommendations (paginated)

**Query Params**

* `page` (int, default 1)
* `page_size` (int, default 10; max 200)
* `event_type` (string, optional; e.g. `system.cpu`)
* `since` (ISO-8601, optional; e.g. `2025-10-25T00:00:00Z`)

**200 OK**

```json
{
  "page": 1,
  "page_size": 5,
  "total": 12,
  "pages": 3,
  "items": [
    {
      "timestamp": "2025-10-27T18:50:22Z",
      "event_type": "system.cpu",
      "source": "recommendation-service",
      "payload": {
        "timestamp": "2025-10-27T18:50:22Z",
        "event_type": "system.cpu",
        "input": {
          "type": "system.cpu",
          "timestamp": "2025-10-27T18:50:22Z",
          "resource": "host-42",
          "labels": { "os": "windows" },
          "metrics": { "usage_pct": 92.5 }
        },
        "recommendations": [
          "⚠️ High CPU (92.5%). Scale up / tune hot paths."
        ]
      }
    }
  ]
}
```

**Empty**

```json
{ "page": 1, "page_size": 10, "total": 0, "pages": 0, "items": [] }
```

**cURL**

```bash
curl -s -H "http://localhost:8080/recommendations?page=1&page_size=5" | jq
```

---

### 3) `POST /recommendations/analyze`

**Purpose:** Analyze a **single event** on-demand (no need to wait for the consumer).

* Uses **LLM** if `OPENAI_API_KEY` is set, otherwise **deterministic rules**.
* By default **does persist** (wired into `storage.py` ).

**Preferred Event Schema**

```json
{
  "type": "system.cpu",            // e.g., system.cpu|system.memory|system.disk|system.net|net.http|service.error_rate|api.payment
  "timestamp": "2025-10-28T12:00:00Z",
  "resource": "host-42",
  "labels": { "os": "windows" },
  "metrics": { "usage_pct": 92.5 }
}
```

**200 OK**

```json
{
  "engine": "llm|rules",
  "input": { ...original payload... },
  "recommendations": [
    "⚠️ High CPU (92.5%). Scale out or optimize hot paths.",
    "Check DB/index hot spots if latency also elevated."
  ]
}
```

**cURL**

```bash
curl -s -X POST "http://localhost:8080/recommendations/analyze" \
  -H "Content-Type: application/json" \
  -d '{
        "type": "system.cpu",
        "timestamp": "2025-10-28T12:00:00Z",
        "resource": "host-42",
        "labels": {"os":"windows"},
        "metrics": {"usage_pct": 92.5}
      }' | jq
```

---

## 📨 RabbitMQ Topology (topic exchanges)

* **Exchanges**

  * `logs` (topic) — incoming metrics from Log Management / producers
  * `recommendations` (topic) — outgoing recommendations from this service

* **Queues**

  * `reco.logs` (bind to `logs` with keys: `system.*`, `service.*`, `api.*`, `net.*`)
  * `reco.debug` (bind to `recommendations` with keys: `#` to see all recos)

> The consumer declares exchanges/queues/bindings on startup (safe to run against an empty broker).

---

## 🧪 Local Testing Tips

* If `/recommendations` returns empty:

  * Ensure `consumer.py` is running and processing messages.
  * Check the DB path is the same for app & consumer (`RECO_DB_PATH`).
  * Tail logs:

    ```bash
    # API
    uvicorn app:app --host 0.0.0.0 --port 8080 --reload

    # Consumer (separate terminal)
    python consumer.py
    ```

---

## 🛠 Environment Examples (`.env`)

```env
# RabbitMQ
RABBIT_URL=amqp://guest:guest@localhost:5672/%2F

RABBIT_LOG_EXCHANGE=logs
RABBIT_RECO_EXCHANGE=recommendations
RABBIT_LOG_QUEUE=reco.logs
RABBIT_LOG_BINDINGS=system.*,service.*,api.*,net.*

# API
SERVICE_VERSION=0.1.0

# DB
RECO_DB_PATH=./data/recommendations.db

# Optional LLM
OPENAI_API_KEY=
```
---

## 📦 Deploying (high level)

* Provision a VM (e.g., AWS EC2), install system Python.
* Clone repo, create venv, `pip install -r requirements.txt`.
* Put your `.env` in the repo folder (use absolute `RECO_DB_PATH`).
* Run with **systemd** and **Nginx** (reverse proxy to port 8080) if you want it always-on.
* Make sure outbound access to your central RabbitMQ is allowed (security groups/firewall).

---

## 📝 License

MIT © 2025 AIMAS Team

---

## Contributors

* Chima Enyeribe
* Oluwatobilola Jesse
* McAdams

---
