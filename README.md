# AIMAS Recommendation Service

## Description

A microservice within the **AIMAS (AI-based Incident Management and Alert System)** ecosystem.

This service listens for live system metrics published by the **Log Management** component via **RabbitMQ**, analyzes them with defined rule logic, and publishes actionable **recommendations** to other AIMAS services such as Alerts or Dashboards.

---

## Overview
```
Prometheus → Log Management → [RabbitMQ: logs]
↓
AIMAS Recommendation Service
↓
[RabbitMQ: recommendations]
↓
Alerts / Dashboard / Reports

```

---

## Features

- 🧠 **Consumes system metrics** (CPU, memory, disk, etc.) from RabbitMQ.  
- ⚙️ **Applies rule-based analysis** via `reco_rules.py`.  
- 📤 **Publishes recommendations** to a shared `recommendations` exchange.  
- 🌐 **Health endpoints** using FastAPI (`/health/live`, `/health/ready`).  
- 🪶 Lightweight, container-ready, no direct Prometheus dependency.

---

## 🗂️ Project Structure

```

aima-recommendation-service/
├── app.py                 # FastAPI app (health endpoints)
├── consumer.py            # Main worker: consumes metrics, applies rules, publishes recommendations
├── reco_rules.py          # Business logic for analyzing metrics
├── rabbitmq_publisher.py  # Utility for publishing recommendations to RabbitMQ
├── .env                   # Environment variables (RabbitMQ config, etc.)
└── requirements.txt       # Python dependencies

````

---

## ⚙️ Environment Variables (`.env`)

```bash
# RabbitMQ configuration
RABBIT_URL=amqp://guest:guest@localhost:5672/%2F

# Exchanges
RABBIT_LOG_EXCHANGE=logs
RABBIT_RECO_EXCHANGE=recommendations

# Queue for incoming logs
RABBIT_LOG_QUEUE=reco.logs

# Optional: service version
SERVICE_VERSION=0.1.0
````

---

## Requirements

* **Python 3.9+**
* **RabbitMQ** instance (local or central)
* Recommended: virtual environment

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## ▶️ Running the Service

Start the health API:

```bash
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

Liveness:

```
GET http://localhost:8080/health/live
```

Readiness (checks RabbitMQ connection if configured):

```
GET http://localhost:8080/health/ready
```

Start the recommendation worker:

```bash
python consumer.py
```

---

## 🩺 Health Endpoints

| Endpoint        | Purpose                                                   | Requires RabbitMQ |
| --------------- | --------------------------------------------------------- | ----------------- |
| `/health/live`  | Basic process liveness                                    | ❌                 |
| `/health/ready` | Deep readiness check (connects to RabbitMQ if configured) | ✅ (optional)      |

---

## 🧩 Future Enhancements

* Integrate **NoSQL** for storing recommendations
* Add **vector search** for similar incident detection
* AI-based recommendation generation using LLMs

---

## Contributors
* Chima Enyeribe
* Oluwatobilola Jesse
* McAdams
---

## 🏷️ License

MIT License © 2025 AIMAS Development Team

```
