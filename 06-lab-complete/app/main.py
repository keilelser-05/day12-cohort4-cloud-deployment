"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key + JWT authentication
  ✅ Rate limiting (sliding window)
  ✅ Cost guard (budget protection)
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown (SIGTERM handler)
  ✅ Stateless design (Redis session history)
  ✅ Security headers & CORS
  ✅ Error handling
"""
import os
import time
import signal
import logging
import json
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key, verify_token, authenticate_user, api_key_header
from app.rate_limiter import check_rate_limit, rate_limiter
from app.cost_guard import check_and_record_cost, cost_guard

# Mock LLM (thay bằng OpenAI/Anthropic khi có API key)
from utils.mock_llm import ask as llm_ask

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

# ─────────────────────────────────────────────────────────
# Stateless Redis Session Management
# ─────────────────────────────────────────────────────────
_redis_session_client = None
if settings.redis_url:
    try:
        import redis
        _redis_session_client = redis.from_url(settings.redis_url, decode_responses=True)
        _redis_session_client.ping()
        logger.info(json.dumps({"event": "redis_connected", "url": settings.redis_url}))
    except Exception as e:
        logger.warning(json.dumps({"event": "redis_unavailable", "warning": str(e)}))
        _redis_session_client = None

_in_memory_sessions: dict[str, dict] = {}


def load_session(session_id: str) -> dict:
    if _redis_session_client:
        try:
            val = _redis_session_client.get(f"session:{session_id}")
            return json.loads(val) if val else {}
        except Exception:
            pass
    return _in_memory_sessions.get(session_id, {})


def save_session(session_id: str, data: dict, ttl_seconds: int = 86400):
    if _redis_session_client:
        try:
            _redis_session_client.setex(f"session:{session_id}", ttl_seconds, json.dumps(data))
            return
        except Exception:
            pass
    _in_memory_sessions[session_id] = data


def append_to_history(session_id: str, role: str, content: str):
    session = load_session(session_id)
    history = session.get("history", [])
    history.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Keep last 20 messages
    if len(history) > 20:
        history = history[-20:]
    session["history"] = history
    save_session(session_id, session)
    return history


# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    time.sleep(0.1)  # simulate init
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))


# ─────────────────────────────────────────────────────────
# App & Middleware
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception as e:
        _error_count += 1
        logger.error(json.dumps({
            "event": "request_error",
            "method": request.method,
            "path": request.url.path,
            "error": str(e),
        }))
        raise


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class TokenRequest(BaseModel):
    username: str
    password: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Your question for the agent")
    session_id: str | None = Field(default=None, description="Session ID for multi-turn history")
    user_id: str | None = Field(default="default_user", description="User ID for budgeting/tracking")


class AskResponse(BaseModel):
    question: str
    answer: str
    session_id: str
    model: str
    timestamp: str


# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────
@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "token": "POST /token (get JWT token)",
            "health": "GET /health (liveness)",
            "ready": "GET /ready (readiness)",
            "metrics": "GET /metrics (protected)",
        },
    }


@app.post("/token", tags=["Auth"])
def login(body: TokenRequest):
    """Obtain a JWT token using username & password."""
    user = authenticate_user(body.username, body.password)
    from app.auth import create_token
    token = create_token(user["username"], user["role"])
    return {"access_token": token, "token_type": "bearer"}


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    # Rate limit check per API key bucket (or 429)
    check_rate_limit(_key[:8])

    user_identifier = body.user_id or _key[:8]
    input_tokens = len(body.question.split()) * 2

    # Cost guard budget check
    check_and_record_cost(input_tokens, 0, user_id=user_identifier)

    session_id = body.session_id or str(uuid.uuid4())
    append_to_history(session_id, "user", body.question)

    logger.info(json.dumps({
        "event": "agent_call",
        "session_id": session_id,
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    answer = llm_ask(body.question)

    output_tokens = len(answer.split()) * 2
    check_and_record_cost(0, output_tokens, user_id=user_identifier)
    append_to_history(session_id, "assistant", answer)

    return AskResponse(
        question=body.question,
        answer=answer,
        session_id=session_id,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/chat/{session_id}/history", tags=["Agent"])
def get_session_history(session_id: str, _key: str = Depends(verify_api_key)):
    """Retrieve multi-turn conversation history for a session."""
    session = load_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    return {
        "session_id": session_id,
        "messages": session.get("history", []),
        "count": len(session.get("history", [])),
    }


@app.delete("/chat/{session_id}", tags=["Agent"])
def delete_session_history(session_id: str, _key: str = Depends(verify_api_key)):
    """Clear conversation history for a session."""
    if _redis_session_client:
        try:
            _redis_session_client.delete(f"session:{session_id}")
        except Exception:
            pass
    _in_memory_sessions.pop(session_id, None)
    return {"status": "deleted", "session_id": session_id}


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    status = "ok"
    redis_status = "disabled"
    if settings.redis_url:
        redis_status = "connected" if _redis_session_client else "disconnected"

    checks = {
        "llm": "mock" if not settings.openai_api_key else "openai",
        "redis": redis_status,
    }
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    if settings.redis_url and _redis_session_client:
        try:
            _redis_session_client.ping()
        except Exception:
            raise HTTPException(503, "Redis connection failed")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    current_cost = cost_guard.get_current_cost("global")
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(current_cost, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(current_cost / settings.daily_budget_usd * 100, 1),
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum, "signal": "SIGTERM"}))

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
