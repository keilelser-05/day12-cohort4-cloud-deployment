"""
Authentication Module — API Key & JWT Token

Supports:
- API Key via header `X-API-Key`
- JWT Bearer token via `Authorization: Bearer <token>`
"""
import os
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings

# API Key setup
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# JWT setup
security_bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

DEMO_USERS = {
    "admin": {"password": "secret", "role": "admin"},
    "student": {"password": "demo123", "role": "user"},
}


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Dependency: verify X-API-Key header.
    Returns the api_key if valid, raises HTTPException otherwise.
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    if api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key


def create_token(username: str, role: str) -> str:
    """Create JWT token with expiration."""
    payload = {
        "sub": username,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security_bearer)) -> dict:
    """
    Dependency: verify JWT bearer token from Authorization header.
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Include header: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[ALGORITHM])
        return {"username": payload["sub"], "role": payload.get("role", "user")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid token.")


def authenticate_user(username: str, password: str) -> dict:
    """Authenticate username and password for token generation."""
    user = DEMO_USERS.get(username)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"username": username, "role": user["role"]}


def get_current_user_or_key(
    api_key: str = Security(api_key_header),
    credentials: HTTPAuthorizationCredentials = Security(security_bearer),
) -> str:
    """
    Unified auth: Accepts either X-API-Key or Bearer Token.
    Returns user identifier.
    """
    if api_key and api_key == settings.agent_api_key:
        return "api-key-user"
    if credentials:
        try:
            payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[ALGORITHM])
            return payload.get("sub", "jwt-user")
        except Exception:
            pass
    raise HTTPException(
        status_code=401,
        detail="Invalid or missing API key. Include header: X-API-Key: <key>",
    )
