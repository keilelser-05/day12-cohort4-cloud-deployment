"""
Comprehensive Test Suite for Production AI Agent
"""
import sys
import os

# Add 06-lab-complete to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

def test_root(client):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert "endpoints" in data
    print("✅ test_root passed")

def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    print("✅ test_health passed")

def test_ready(client):
    res = client.get("/ready")
    assert res.status_code == 200
    assert res.json().get("ready") is True
    print("✅ test_ready passed")

def test_unauthorized(client):
    res = client.post("/ask", json={"question": "hello"})
    assert res.status_code == 401
    print("✅ test_unauthorized passed")

def test_ask_authorized(client):
    headers = {"X-API-Key": settings.agent_api_key}
    res = client.post(
        "/ask",
        headers=headers,
        json={"question": "What is Docker?", "session_id": "session-123"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "Docker" in data["question"] or "answer" in data
    assert data["session_id"] == "session-123"
    print("✅ test_ask_authorized passed")

def test_session_history(client):
    headers = {"X-API-Key": settings.agent_api_key}
    # Ask second turn
    client.post(
        "/ask",
        headers=headers,
        json={"question": "What is cloud deployment?", "session_id": "session-123"},
    )
    # Check history
    res = client.get("/chat/session-123/history", headers=headers)
    assert res.status_code == 200
    history = res.json()
    assert history["count"] >= 4  # 2 user + 2 assistant messages
    print("✅ test_session_history passed")

def test_metrics(client):
    headers = {"X-API-Key": settings.agent_api_key}
    res = client.get("/metrics", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "total_requests" in data
    assert "daily_budget_usd" in data
    print("✅ test_metrics passed")

def test_jwt_token_auth(client):
    # Login
    res = client.post("/token", json={"username": "admin", "password": "secret"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    assert len(token) > 10
    print("✅ test_jwt_token_auth passed")

if __name__ == "__main__":
    print("\nRunning comprehensive agent test suite...")
    with TestClient(app) as client:
        test_root(client)
        test_health(client)
        test_ready(client)
        test_unauthorized(client)
        test_ask_authorized(client)
        test_session_history(client)
        test_metrics(client)
        test_jwt_token_auth(client)
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!\n")


