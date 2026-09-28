# Deployment Information — Production AI Agent

## Service Overview

| Thuộc tính | Giá trị |
|------------|---------|
| **Service Name** | Production AI Agent |
| **Public URL** | `https://day12-agent-production.up.railway.app` (Railway) / `https://day12-agent.onrender.com` (Render) |
| **Deployment Platform** | Railway / Render (Docker runtime) |
| **Healthcheck Path** | `/health` |
| **Base Image** | `python:3.11-slim` (Multi-stage build) |

---

## Architecture

```
Client ──► Cloud Load Balancer (HTTPS / 443)
                 │
                 ▼
         FastAPI Container ($PORT)
                 │
                 ├─► X-API-Key / JWT Auth
                 ├─► Rate Limiter (20 req/min)
                 ├─► Cost Guard ($5/day budget)
                 ├─► Mock / OpenAI LLM
                 └─► Redis Cluster (Stateless Sessions)
```

---

## Test Commands

### 1. Health Check (Liveness Probe)

```bash
curl -i https://day12-agent-production.up.railway.app/health
```

**Expected Response (HTTP 200):**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 128.4,
  "total_requests": 14,
  "checks": {
    "llm": "mock",
    "redis": "connected"
  },
  "timestamp": "2026-09-28T03:25:00Z"
}
```

### 2. Readiness Probe

```bash
curl -i https://day12-agent-production.up.railway.app/ready
```

**Expected Response (HTTP 200):**
```json
{
  "ready": true
}
```

### 3. Authentication Test (Unauthorized Check)

```bash
# Không có header X-API-Key -> 401 Unauthorized
curl -i -X POST https://day12-agent-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

**Expected Response (HTTP 401):**
```json
{
  "detail": "Invalid or missing API key. Include header: X-API-Key: <key>"
}
```

### 4. Ask Endpoint (Authorized)

```bash
curl -i -X POST https://day12-agent-production.up.railway.app/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain Docker multi-stage builds", "session_id": "test-session-1"}'
```

**Expected Response (HTTP 200):**
```json
{
  "question": "Explain Docker multi-stage builds",
  "answer": "Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!",
  "session_id": "test-session-1",
  "model": "gpt-4o-mini",
  "timestamp": "2026-09-28T03:26:00Z"
}
```

### 5. Multi-turn Conversation History

```bash
# Kiểm tra lịch sử cuộc trò chuyện
curl -i https://day12-agent-production.up.railway.app/chat/test-session-1/history \
  -H "X-API-Key: dev-key-change-me"
```

---

## Environment Variables Configuration

| Biến môi trường | Mục đích | Giá trị mẫu |
|-----------------|----------|-------------|
| `PORT` | Cổng HTTP mà ứng dụng lắng nghe | `8000` (hoặc do Cloud cấp phát động) |
| `ENVIRONMENT` | Môi trường triển khai | `production` |
| `APP_NAME` | Tên định danh ứng dụng | `Production AI Agent` |
| `APP_VERSION` | Phiên bản mã nguồn | `1.0.0` |
| `AGENT_API_KEY` | Khóa bí mật API xác thực | `dev-key-change-me` |
| `JWT_SECRET` | Secret ký chữ ký số JWT | `dev-jwt-secret` |
| `REDIS_URL` | URL kết nối Redis Cluster/Instance | `redis://default:password@host:6379/0` |
| `DAILY_BUDGET_USD` | Ngân sách token giới hạn mỗi ngày | `5.0` |
| `RATE_LIMIT_PER_MINUTE` | Tối đa request mỗi phút cho mỗi IP/Key | `20` |
| `ALLOWED_ORIGINS` | Danh sách domain CORS được cấp phép | `*` |

---

## Deployment Instructions

### Deploy to Railway:

```bash
# 1. Cài đặt Railway CLI
npm i -g @railway/cli

# 2. Đăng nhập và khởi tạo
railway login
railway init

# 3. Thiết lập biến môi trường
railway variables set AGENT_API_KEY=dev-key-change-me
railway variables set ENVIRONMENT=production

# 4. Triển khai
railway up

# 5. Lấy public domain
railway domain
```

### Deploy to Render:

1. Đẩy code lên GitHub repository: `https://github.com/keilelser-05/day12-cohort4-cloud-deployment`
2. Đăng nhập [render.com](https://render.com) -> New -> **Blueprint**
3. Chọn repo và Render sẽ tự động nạp cấu hình từ `render.yaml`
4. Cung cấp các biến bảo mật trong tab Settings -> Environment
5. Nhấn **Deploy** và nhận domain HTTPS trực tiếp.
