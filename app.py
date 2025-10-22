# app.py
import os
import time
import pika
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
#from prometheus_client import query_prometheus

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
