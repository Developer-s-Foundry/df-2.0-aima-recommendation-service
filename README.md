# AIMAS Recommendation Service

A microservice within the **AIMAS (AI-based Incident Management and Alert System)** ecosystem.  

This service listens to live system or application metrics published by the **Log Management** component through **RabbitMQ**, analyzes them using either **rule-based logic** or **LLM-based reasoning**, and publishes actionable **recommendations** to other AIMAS services such as **Alerts**, **Dashboards**, or **Reports**.

---

## Data Flow Overview

```
Prometheus → Log Management → [RabbitMQ Exchange: logs]
                     ↓
         AIMAS Recommendation Service
   ├─ consumer.py      → rule-based & AI/LLM-driven analysis
                     ↓
         [RabbitMQ Exchange: recommendations]
                     ↓
          Alerts / Dashboard / Reports
```

---

## Key Features

- **Dual Mode Analysis** — choose between rule-based or AI-powered recommendations  
- **RabbitMQ Integration** — consumes from `logs` exchange, publishes to `recommendations`  
- **Metric Coverage** — CPU, memory, disk, network, and service performance events  
- **FastAPI Health Endpoints** — `/health/live`, `/health/ready`  
- 🪶 **Lightweight & Container-Ready** — minimal dependencies, plug-and-play  

---

## 🗂️ Project Structure

```
aima-recommendation-service/
├── app.py                  # FastAPI app (health endpoints)
├── consumer.py             # Rule & OpenAI-based recommendation worker
├── rabbitmq_publisher.py   # Shared publisher utility
├── rules/                  # Modular rule packs (CPU, network, etc.)
├── .env                    # Environment configuration
├── requirements.txt        # Python dependencies
└── Prometheus_win_exporter_rabbitmq.md  # Step-by-step setup guide
```

---

## Environment Variables (`.env`)

```bash
# RabbitMQ connection
RABBIT_URL=amqp://guest:guest@localhost:5672/%2F

# Exchanges
RABBIT_LOG_EXCHANGE=logs
RABBIT_RECO_EXCHANGE=recommendations

# Queues
RABBIT_LOG_QUEUE=reco.logs

# Optional service metadata
SERVICE_VERSION=0.1.0
```

---

## Requirements

- **Python 3.9+**
- **RabbitMQ** (local or central broker)
- **Prometheus + Windows Exporter** (for metrics collection)  
  👉 For a detailed installation guide, see  
  **[`Prometheus_win_exporter_rabbitmq.md`](Prometheus_win_exporter_rabbitmq.md)**

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## ▶️ Running the Service

### 1. Start the Health API

```bash
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

- **Liveness:** `GET http://localhost:8080/health/live`  
- **Readiness:** `GET http://localhost:8080/health/ready` (also checks RabbitMQ)

### 2. Start the Rule-Based Worker

```bash
python consumer.py
```

### 3. Start the AI/LLM Worker (optional)

```bash
python consumer_llm.py
```

> The LLM worker uses your `OPENAI_API_KEY` and prints the generated recommendations directly to your terminal.

---

## 🩺 Health Endpoints

| Endpoint | Purpose | RabbitMQ Required |
|-----------|----------|------------------|
| `/health/live` | Process liveness check | ❌ |
| `/health/ready` | Readiness & RabbitMQ connectivity | ✅ (optional) |

---

## Future Enhancements

- Integrate NoSQL storage for recommendation history  
- Add vector search for similar incident detection  
- Enhance AI model context awareness and confidence scoring  

---

## Contributors
- Chima Enyeribe  
- Oluwatobilola Jesse  
- McAdams  

---

## License
MIT License © 2025 AIMAS Development Team  
