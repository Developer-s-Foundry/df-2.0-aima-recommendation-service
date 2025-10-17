# app.py
from fastapi import FastAPI
from prometheus_client import query_prometheus
from reco_rules import analyze_cpu, analyze_memory, analyze_disk

# app = FastAPI(title="AIMAS Recommendation Service")


import os
import time
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

# Optional: only used for readiness check when RABBIT_URL is set
import pika

load_dotenv()

SERVICE_NAME = "aimas-recommendation"
VERSION = os.getenv("SERVICE_VERSION", "0.1.0")
RABBIT_URL: Optional[str] = os.getenv("RABBIT_URL")  # e.g. amqps://user:pass@host:5671/%2Fvhost

app = FastAPI(title="AIMAS Recommendation Service", version=VERSION)


class HealthResponse(BaseModel):
    status: str              # "ok" | "degraded" | "not_ready"
    service: str
    version: str
    time: float
    rabbitmq: dict


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
def live():
    """
    Liveness: process is up and responsive.
    Does NOT require RabbitMQ to be configured or reachable.
    """
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=VERSION,
        time=time.time(),
        rabbitmq={
            "configured": bool(RABBIT_URL),
            "reachable": None,   # not checked on liveness
            "error": None
        },
    )


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
def ready():
    """
    Readiness: deep check. If RABBIT_URL is provided, try to connect quickly.
    If RABBIT_URL is missing, return 'degraded' (service is up, broker not configured yet).
    """
    if not RABBIT_URL:
        return HealthResponse(
            status="degraded",
            service=SERVICE_NAME,
            version=VERSION,
            time=time.time(),
            rabbitmq={
                "configured": False,
                "reachable": None,
                "error": "RABBIT_URL not configured"
            },
        )

    # Try a short RabbitMQ connect/close
    try:
        params = pika.URLParameters(RABBIT_URL)
        # Keep timeouts low so the endpoint returns fast
        params.socket_timeout = 3
        params.heartbeat = 0
        conn = pika.BlockingConnection(params)
        conn.close()
        return HealthResponse(
            status="ok",
            service=SERVICE_NAME,
            version=VERSION,
            time=time.time(),
            rabbitmq={
                "configured": True,
                "reachable": True,
                "error": None
            },
        )
    except Exception as e:
        return HealthResponse(
            status="not_ready",
            service=SERVICE_NAME,
            version=VERSION,
            time=time.time(),
            rabbitmq={
                "configured": True,
                "reachable": False,
                "error": repr(e)
            },
        )


@app.get("/recommend/system")
def recommend_system():
    """
    Collect CPU, Memory, and Disk metrics → Return combined recommendations.
    """
    # --- CPU ---
    cpu_query = 'avg(rate(windows_cpu_time_total{mode!="idle"}[5m])) * 100'
    cpu_result = query_prometheus(cpu_query)
    cpu_values = [float(r["value"][1]) for r in cpu_result if "value" in r]
    cpu_recos = analyze_cpu(cpu_values)

    # --- Memory ---
    mem_total_query = 'windows_os_physical_memory_bytes / 1024 / 1024 / 1024'
    mem_free_query = 'windows_memory_available_bytes / 1024 / 1024 / 1024'

    mem_total = query_prometheus(mem_total_query)
    mem_free = query_prometheus(mem_free_query)

    mem_total_gb = float(mem_total[0]["value"][1]) if mem_total else None
    mem_free_gb = float(mem_free[0]["value"][1]) if mem_free else None
    mem_recos = analyze_memory(mem_total_gb, mem_free_gb)

    # --- Disk ---
    disk_total_query = 'windows_logical_disk_size_bytes{volume="C:"} / 1024 / 1024 / 1024'
    disk_free_query = 'windows_logical_disk_free_bytes{volume="C:"} / 1024 / 1024 / 1024'

    disk_total = query_prometheus(disk_total_query)
    disk_free = query_prometheus(disk_free_query)

    disk_total_gb = float(disk_total[0]["value"][1]) if disk_total else None
    disk_free_gb = float(disk_free[0]["value"][1]) if disk_free else None
    disk_recos = analyze_disk(disk_total_gb, disk_free_gb, "C:")

    return {
        "cpu_usage_samples": cpu_values,
        "memory": {"total_gb": mem_total_gb, "free_gb": mem_free_gb},
        "disk": {"total_gb": disk_total_gb, "free_gb": disk_free_gb},
        "recommendations": cpu_recos + mem_recos + disk_recos
    }
