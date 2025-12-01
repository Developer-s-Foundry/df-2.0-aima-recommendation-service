# app.py
import os
import json
import time
import pika
import hmac # added 1
import hashlib # added 2
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional, List
from fastapi import FastAPI, Request, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response
from storage import init_db, query_recommendations_paginated, get_user_projects

# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST

# Rule packs (deterministic)
from rules.cpu_rules import CPURulePack
from rules.memory_rules import MemoryRulePack
from rules.disk_rules import DiskRulePack
from rules.payment_rules import PaymentAPIRulePack
from rules.system_net_rules import SystemNetRulePack
from rules.error_rate_rules import ServiceErrorRateRulePack
from rules.network_http_rules import NetworkHttpRulePack
from rules.generic_rules import GenericRulePack

load_dotenv()

SERVICE_NAME = "recommendation-service"
VERSION = os.getenv("SERVICE_VERSION", "0.1.0")
RABBIT_URL: Optional[str] = os.getenv("RABBIT_URL")

# =============================================================================
# PROMETHEUS METRICS
# =============================================================================

# 1. HTTP Request Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests received',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint']
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'Number of HTTP requests currently being processed'
)

# 2. Application-Specific Metrics
recommendations_generated_total = Counter(
    'recommendations_generated_total',
    'Total recommendations generated',
    ['mode', 'event_type']
)

events_analyzed_total = Counter(
    'events_analyzed_total',
    'Total events analyzed',
    ['event_type', 'mode']
)

# 3. Health Metrics
service_info = Info(
    'service',
    'Service information'
)
service_info.info({
    'name': SERVICE_NAME,
    'version': VERSION
})

rabbitmq_connected = Gauge(
    'rabbitmq_connected',
    'RabbitMQ connection status (1=connected, 0=disconnected)'
)

# =============================================================================

app = FastAPI(title="AIMAS Recommendation Service")

# -----------------------------
# PROMETHEUS MIDDLEWARE
# -----------------------------
@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    """
    Middleware to automatically track all HTTP requests.
    Measures: request count, latency, and requests in progress.
    """
    # Skip metrics for the /metrics endpoint itself to avoid recursion
    if request.url.path == "/metrics":
        return await call_next(request)

    # Track requests in progress
    http_requests_in_progress.inc()

    # Start timer
    start_time = time.time()

    try:
        # Process the request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Record metrics
        http_requests_total.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code
        ).inc()

        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)

        return response

    except Exception as e:
        # Even if there's an error, track it
        duration = time.time() - start_time

        http_requests_total.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=500
        ).inc()

        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)

        raise e

    finally:
        # Always decrement in-progress counter
        http_requests_in_progress.dec()

# -----------------------------
# DB init
# -----------------------------
@app.on_event("startup")
async def startup_event():
    init_db()

# -----------------------------
# Auth (Gateway Signature)
# -----------------------------
# We treat this as the shared secret between the API Gateway and this service.
# Prefer GATEWAY_SECRET_KEY, but fall back to API_KEYS[0] for backwards compatibility.
GATEWAY_SECRET_KEY = os.getenv("GATEWAY_SECRET_KEY", "").strip()

if not GATEWAY_SECRET_KEY:
    _API_KEYS_RAW = os.getenv("API_KEYS", "")
    if _API_KEYS_RAW:
        GATEWAY_SECRET_KEY = _API_KEYS_RAW.split(",")[0].strip()


def _compute_gateway_signature(
    secret: str,
    method: str,
    path: str,
    user_id: str,
    timestamp: str,
    service_name: str,
) -> str:
    """
    Example signature scheme: HMAC-SHA256 over a canonical string.

    Adjust this to match whatever your API Gateway actually does.
    """
    payload = "\n".join([method.upper(), path, user_id, timestamp, service_name])
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def require_gateway_auth(
    request: Request,
    x_gateway_signature: Optional[str] = Header(None, alias="X-Gateway-Signature"),
    x_gateway_timestamp: Optional[str] = Header(None, alias="X-Gateway-Timestamp"),
    z_gateway_timestamp: Optional[str] = Header(None, alias="Z-Gateway-Timestamp"),
    x_service_name: Optional[str] = Header(None, alias="X-Service-Name"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-Id"),  # optional for now
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),        # optional, not in HMAC
):
    """
    Dependency that verifies that the request really came through the API Gateway.

    - Uses GATEWAY_SECRET_KEY (or first API_KEYS entry) as the shared secret.
    - Verifies presence of required headers.
    - Validates timestamp freshness.
    - Recomputes and checks the HMAC signature.
    """

    # If no secret is configured, leave endpoints open (dev mode).
    if not GATEWAY_SECRET_KEY:
        #return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway secret not configured on server",
        )

    x_gateway_timestamp = x_gateway_timestamp or z_gateway_timestamp

    # 1) Check for required headers
    missing = []
    if not x_gateway_signature:
        missing.append("X-Gateway-Signature")
    if not x_gateway_timestamp:
        missing.append("X-Gateway-Timestamp/Z-Gateway-Timestamp")
    if not x_service_name:
        missing.append("X-Service-Name")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing required gateway headers: {', '.join(missing)}",
        )

    # 2) Basic timestamp validation: must be an integer (nanoseconds)
    try:
        int(x_gateway_timestamp)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid gateway timestamp format",
        )
    

    # 3) Optionally validate service name matches this service
    expected_service_name = SERVICE_NAME
    if x_service_name != expected_service_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request not intended for this service",
        )

    # 4) Recompute expected signature using the exact same scheme as Go:
    # encryptKey := fmt.Sprintf("%s:%s", config.Name, timestamp)
    encrypt_key = f"{x_service_name}:{x_gateway_timestamp}"
    expected_sig = hmac.new(
        GATEWAY_SECRET_KEY.encode("utf-8"),
        encrypt_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, x_gateway_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid gateway signature",
        )

    # If we reach here, the request is trusted as coming via the gateway.
    # Return the user_id so endpoints can use it for filtering
    return {"user_id": x_user_id, "request_id": x_request_id}


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
        rabbitmq_connected.set(0)  # Update Prometheus metric
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
        rabbitmq_connected.set(1)  # Update Prometheus metric
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
        rabbitmq_connected.set(0)  # Update Prometheus metric
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


# -----------------------------
# PROMETHEUS METRICS ENDPOINT
# -----------------------------
@app.get("/metrics", tags=["monitoring"])
def metrics():
    """
    Prometheus metrics endpoint.
    Returns all collected metrics in Prometheus format.
    This endpoint is scraped by Prometheus server.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# -----------------------------
# Deterministic rule engine (for POST /analyze fallback)
# -----------------------------
_SPECIFIC_RULES = [
    CPURulePack(),
    MemoryRulePack(),
    DiskRulePack(),
    SystemNetRulePack(),
    PaymentAPIRulePack(),
    ServiceErrorRateRulePack(),
    NetworkHttpRulePack(),
]
_GENERIC_RULE = GenericRulePack()

def _normalize_metrics(event: dict) -> dict:
    m = (event.get("metrics") or {})
    et = event.get("type", "")
    # small compat shim
    if et in ("system.cpu", "host.cpu"):
        if "usage_pct" not in m and "used_pct" in m:
            m["usage_pct"] = m["used_pct"]
    event["metrics"] = m
    return event

def evaluate_rules(event: dict) -> List[str]:
    et = event.get("type")
    recos: List[str] = []
    for pack in _SPECIFIC_RULES:
        if pack.supports(et):
            recos += pack.evaluate(event)
    if not recos:
        recos += _GENERIC_RULE.evaluate(event)
    # de-dup
    return list(dict.fromkeys(recos))

# -----------------------------
# Optional LLM support (for POST /analyze)
# -----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "400"))
USE_LLM = bool(OPENAI_API_KEY)

_OPENAI_CLIENT = None
def _ensure_openai():
    global _OPENAI_CLIENT
    if not USE_LLM:
        return None
    if _OPENAI_CLIENT is None:
        from openai import OpenAI
        _OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)
    return _OPENAI_CLIENT

def llm_analyze(event: dict) -> str:
    client = _ensure_openai()
    if client is None:
        return "⚠️ OPENAI_API_KEY not set; LLM analysis unavailable."
    pretty = json.dumps(event, ensure_ascii=False, indent=2)
    system_msg = (
        "You are an SRE/Observability assistant. Given a JSON event with metrics/logs, "
        "produce concise, actionable recommendations. Focus on severity, key signals, "
        "likely causes, and next steps."
    )
    user_msg = (
        "Analyze the following event and respond in this format:\n"
        "Severity: <LOW|MODERATE|HIGH|CRITICAL>\n"
        "Signals: • <bullet 1>\n"
        "         • <bullet 2>\n"
        "Recommendations:\n"
        "1) <step 1>\n"
        "2) <step 2>\n"
        "3) <step 3>\n\n"
        "JSON:\n" + pretty
    )
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=OPENAI_TEMPERATURE,
        max_tokens=OPENAI_MAX_TOKENS,
    )
    return (resp.choices[0].message.content or "").strip()

def parse_llm_recos(text: str) -> List[str]:
    recos: List[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if s[0].isdigit() and (") " in s or ". " in s):
            idx = s.find(") ")
            if idx == -1:
                idx = s.find(". ")
            if idx != -1:
                recos.append(s[idx+2:].strip())
    return recos

# @app.get("/headers")
# async def get_headers(request: Request):
#     return {"headers": dict(request.headers)}


# -----------------------------
# DEBUG ENDPOINT: Gateway Signature Verification
# -----------------------------
# @app.post("/debug/gateway", summary="Debug and inspect gateway signature verification")
# async def debug_gateway_signature(
#     request: Request,
#     x_gateway_signature: Optional[str] = Header(None, alias="x-gateway-signature"),
#     x_gateway_timestamp: Optional[str] = Header(None, alias="x-gateway-timestamp"),
#     z_gateway_timestamp: Optional[str] = Header(None, alias="z-gateway-timestamp"),
#     x_request_id: Optional[str] = Header(None, alias="x-request-id"),
#     x_service_name: Optional[str] = Header(None, alias="x-service-name"),
#     x_user_id: Optional[str] = Header(None, alias="x-user-id"),
# ):
#     """
#     Debug helper: shows exactly what headers the service received,
#     how the expected signature was computed, and whether it matches.
#     """

#     gateway_timestamp = x_gateway_timestamp or z_gateway_timestamp
#     missing = []
#     if not x_gateway_signature:
#         missing.append("x-gateway-signature")
#     if not gateway_timestamp:
#         missing.append("x-gateway-timestamp/z-gateway-timestamp")
#     if not x_service_name:
#         missing.append("x-service-name")

#     if missing:
#         return {
#             "status": "error",
#             "message": f"Missing required headers: {', '.join(missing)}",
#             "received": dict(request.headers),
#         }

#     if not GATEWAY_SECRET_KEY:
#         return {
#             "status": "error",
#             "message": "GATEWAY_SECRET_KEY not configured on server",
#         }

#     # Compute expected signature using the same Go logic:
#     encrypt_key = f"{x_service_name}:{gateway_timestamp}"
#     expected_sig = hmac.new(
#         GATEWAY_SECRET_KEY.encode("utf-8"),
#         encrypt_key.encode("utf-8"),
#         hashlib.sha256,
#     ).hexdigest()

#     # Compare
#     match = hmac.compare_digest(expected_sig, x_gateway_signature)

#     return {
#         "status": "ok" if match else "mismatch",
#         "match": match,
#         "received_headers": {
#             "x-gateway-signature": x_gateway_signature,
#             "x-gateway-timestamp": gateway_timestamp,
#             "x-request-id": x_request_id,
#             "x-service-name": x_service_name,
#             "x-user-id": x_user_id,
#         },
#         "computed": {
#             "encrypt_key": encrypt_key,
#             "expected_signature": expected_sig,
#         },
#         "note": (
#             "This endpoint is for debugging only. Remove or protect it "
#             "before deploying to production."
#         ),
#     }


@app.get(
    "/recommendations",
    summary="Fetch recent recommendations",
)
def get_recommendations(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    since: Optional[str] = Query(None, description="ISO timestamp filter (optional)"),
    event_type: Optional[str] = Query(None, description="Filter by event type, e.g., system.cpu"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    auth_context: dict = Depends(require_gateway_auth),
):
    """
    Fetch recommendations for the authenticated user.
    Users can only see recommendations that belong to them.
    Optionally filter by project_id to see recommendations for a specific project.
    """
    # Extract user_id from the auth context (provided by gateway)
    user_id = auth_context.get("user_id")

    # Query recommendations filtered by user_id and optionally project_id
    items, total = query_recommendations_paginated(
        page=page,
        page_size=page_size,
        since=since,
        event_type=event_type,
        user_id=user_id,
        project_id=project_id
    )
    pages = (total + page_size - 1) // page_size if page_size else 1
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
        "items": items,
        "user_id": user_id,  # Include in response so user knows which user's data they're seeing
        "project_id": project_id,
    }


@app.get(
    "/recommendations/projects",
    summary="Get all projects with recommendations for the authenticated user",
)
def get_user_projects_endpoint(
    auth_context: dict = Depends(require_gateway_auth),
):
    """
    Returns a list of all projects that have recommendations for the authenticated user.
    Each project includes:
    - project_id: The project identifier
    - recommendation_count: Number of recommendations for this project
    - latest_timestamp: Timestamp of the most recent recommendation

    This is useful for showing a user which projects they can view recommendations for.
    """
    user_id = auth_context.get("user_id")
    projects = get_user_projects(user_id=user_id)

    return {
        "user_id": user_id,
        "project_count": len(projects),
        "projects": projects,
    }


# -----------------------------
# POST /recommendations/analyze  (AUTH)
# -----------------------------
@app.post(
        "/recommendations/analyze",
        summary="Analyze a single event JSON and return recommendations",
        dependencies=[Depends(require_gateway_auth)])
def analyze_event(event: dict):
    """
    Accepts a single event in the contract schema:
      type, timestamp, resource, labels, metrics
    Returns recommendations from LLM if configured; otherwise from rules.
    """
    # Default timestamp if missing
    if "timestamp" not in event:
        event["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    event = _normalize_metrics(event)
    et = event.get("type", "unknown.event")

    if USE_LLM:
        # Track event analyzed
        events_analyzed_total.labels(event_type=et, mode="llm").inc()

        text = llm_analyze(event)
        recos = parse_llm_recos(text)

        # Track recommendations generated
        if recos:
            recommendations_generated_total.labels(mode="llm", event_type=et).inc(len(recos))

        return {
            "mode": "llm",
            "event_type": et,
            "recommendations_text": text,
            "recommendations": recos,
        }
    else:
        # Track event analyzed
        events_analyzed_total.labels(event_type=et, mode="rules").inc()

        recos = evaluate_rules(event)

        # Track recommendations generated
        if recos:
            recommendations_generated_total.labels(mode="rules", event_type=et).inc(len(recos))

        return {
            "mode": "rules",
            "event_type": et,
            "recommendations": recos,
        }
