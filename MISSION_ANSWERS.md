# Day 12 Lab - Mission Answers

**Student Name:** AI Engineer Student  
**Student ID:** AICB-P1-DAY12  
**Date:** 2026-09-28  
**Repository:** [keilelser-05/day12-cohort4-cloud-deployment](https://github.com/keilelser-05/day12-cohort4-cloud-deployment)

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

Khi phân tích `01-localhost-vs-production/develop/app.py`, phát hiện các anti-patterns sau:

1. **Hardcoded Secrets trong mã nguồn:**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - **Hậu quả:** Khi commit mã nguồn lên GitHub/GitLab, credentials bị lộ hoàn toàn, dẫn đến nguy cơ rò rỉ dữ liệu hoặc tài khoản LLM bị cạn tiền do bị lạm dụng.

2. **Thiếu Configuration Management (12-Factor App III):**
   - Các thông số (`DEBUG = True`, `MAX_TOKENS = 500`) bị gán cứng thay vì đọc từ environment variables. Không thể thay đổi hành vi giữa môi trường test, staging và production mà không phải sửa code.

3. **Dùng `print()` thay vì Structured Logging & Lộ Secrets ra log:**
   - Dùng `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` không chỉ in thông tin nhạy cảm vào stdout mà còn thiếu định dạng chuẩn (JSON, timestamp, log level). Không thể thu thập, lọc và phân tích qua các hệ thống tập trung như Datadog, Loki hay CloudWatch.

4. **Thiếu Health Check & Readiness Check endpoints:**
   - Không có endpoint `/health` hay `/ready`. Các nền tảng điều phối container (Kubernetes, Docker Swarm, Railway, Render) không thể biết container còn sống (liveness) hay sẵn sàng tiếp nhận request (readiness) để tự động restart hoặc ngắt traffic khi có sự cố.

5. **Hardcoded Host và Port:**
   - `host="localhost"` chỉ cho phép truy cập cục bộ từ loopback interface, khiến container không thể tiếp nhận request từ bên ngoài (cần phải bind `0.0.0.0`).
   - `port=8000` bị gán cứng, không đọc biến môi trường `PORT` mà các nền tảng PaaS (Railway, Render, Heroku) inject động vào runtime.

6. **Chạy Debug Mode (`reload=True`) trong môi trường chạy:**
   - Bật file watcher reload gây tiêu tốn tài nguyên CPU/Memory không cần thiết và tiềm ẩn rủi ro bảo mật nghiêm trọng.

7. **Không xử lý Graceful Shutdown:**
   - Không bắt tín hiệu `SIGTERM` / `SIGINT`. Khi container bị kill/scale down, các request đang xử lý dở dang (in-flight requests) sẽ bị ngắt đột ngột, gây lỗi 502/504 cho người dùng hoặc làm mất dữ liệu.

---

### Exercise 1.3: Comparison Table (`develop` vs `production`)

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
|---------|---------------------------|----------------------------------|---------------------|
| **Config** | Hardcode trực tiếp trong file code | Quản lý tập trung qua `pydantic-settings` / biến môi trường (`.env`) | Tuân thủ 12-Factor App (Config). Đảm bảo bảo mật secrets, dễ dàng cấu hình linh hoạt giữa Dev / Staging / Prod mà không cần build lại image. |
| **Health Check** | Không có | Có đầy đủ `/health` (Liveness) và `/ready` (Readiness) | Giúp container orchestrator / load balancer tự động phát hiện instance lỗi để restart hoặc tạm ngưng điều hướng traffic, đảm bảo độ sẵn sàng cao (High Availability). |
| **Logging** | `print()` không cấu trúc, in cả secret ra log | Structured JSON logging (`{"ts": "...", "lvl": "...", "msg": "..."}`) | Log có cấu trúc dễ dàng parse và filter tự động trên các hệ thống giám sát tập trung (ELK, Loki, Datadog), không làm rò rỉ secret. |
| **Shutdown** | Đột ngột (Process bị ngắt ngay lập tức) | Graceful shutdown qua `lifespan` và `SIGTERM` handler | Cho phép container hoàn thành nốt các request đang xử lý (in-flight requests) và đóng kết nối an toàn trước khi dừng hoàn toàn. |
| **Host Binding** | `localhost` (127.0.0.1) | `0.0.0.0` | Container có thể nhận kết nối từ bridge network và load balancer bên ngoài. |
| **Port Binding** | Cố định `8000` | Đọc động từ biến môi trường `PORT` (`os.getenv("PORT", 8000)`) | Bắt buộc đối với các nền tảng PaaS / Serverless như Railway, Render, GCP Cloud Run nơi port được cấp phát động. |
| **Security & CORS** | Không kiểm soát CORS hay Security Headers | Cấu hình `CORSMiddleware`, gán `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` | Ngăn chặn các cuộc tấn công Clickjacking, MIME-sniffing và hạn chế Cross-Origin không hợp lệ. |

---

## Part 2: Docker Containerization

### Exercise 2.1: Dockerfile Questions

1. **Base image là gì?**
   - Trong `02-docker/develop/Dockerfile`, base image là `python:3.11` (full Debian image dung lượng lớn ~1 GB).
   - Trong `02-docker/production/Dockerfile`, base image là `python:3.11-slim` (bản tinh gọn loại bỏ các package hệ thống dư thừa, kích thước chỉ ~150 MB).

2. **Working directory là gì?**
   - Working directory được đặt là `WORKDIR /app` (trong production builder là `/build` hoặc `/app`). Lệnh này thiết lập thư mục làm việc mặc định cho tất cả các lệnh `RUN`, `CMD`, `COPY`, `ADD` tiếp theo trong image.

3. **Tại sao `COPY requirements.txt` trước?**
   - Để tận dụng cơ chế **Docker Layer Caching**. Các dependencies trong `requirements.txt` thay đổi ít thường xuyên hơn mã nguồn ứng dụng. Bằng cách copy `requirements.txt` và chạy `pip install` trước khi copy mã nguồn, Docker sẽ cache lại layer cài đặt thư viện. Khi lập trình viên thay đổi code, Docker chỉ cần build lại layer copy code mà không phải tốn thời gian tải lại toàn bộ dependencies.

4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `ENTRYPOINT`: Xác định câu lệnh/chương trình thực thi cố định luôn chạy khi container khởi động.
   - `CMD`: Cung cấp các đối số mặc định cho `ENTRYPOINT` hoặc định nghĩa lệnh mặc định nếu không khai báo `ENTRYPOINT`. `CMD` có thể dễ dàng bị ghi đè bởi các tham số truyền vào khi chạy `docker run <image> <command>`, trong khi `ENTRYPOINT` yêu cầu cờ `--entrypoint` mới ghi đè được.

---

### Exercise 2.3: Image Size Comparison

| Build Stage | Image Tag | Image Size | Ghi chú |
|-------------|-----------|------------|---------|
| **Develop (Single-stage)** | `agent:develop` | ~1.05 GB | Chứa full Debian build tools, dev libraries, apt cache |
| **Production (Multi-stage)** | `agent:production` | ~215 MB | Dùng `python:3.11-slim`, chỉ copy wheels từ builder, loại bỏ gcc |
| **Difference** | Giảm dung lượng | **Giảm ~79.5%** | Tốc độ deploy nhanh hơn, ít lỗ hổng CVE hơn |

**Lợi ích của Multi-stage build:**
- **Stage 1 (Builder):** Dùng để compile và cài đặt dependencies có chứa C extensions (cần `gcc`, `libpq-dev`). Toàn bộ tool biên dịch và cache chỉ tồn tại ở stage này.
- **Stage 2 (Runtime):** Khởi tạo từ image slim sạch hoàn toàn. Chỉ copy thư mục `.local` đã cài đặt sẵn từ Stage 1 sang và chạy ứng dụng dưới quyền **non-root user** (`agent`). Kích thước image cực kỳ nhỏ gọn và bảo mật cao.

---

### Exercise 2.4: Docker Compose Architecture

```
                 Internet / Clients
                         │
                         ▼
             ┌───────────────────────┐
             │   Nginx (Port 80)     │
             │   Reverse Proxy & LB  │
             └───────────┬───────────┘
                         │
         ┌───────────────┼───────────────┐
         │ (Round Robin) │               │
         ▼               ▼               ▼
   ┌───────────┐   ┌───────────┐   ┌───────────┐
   │  agent_1  │   │  agent_2  │   │  agent_3  │
   │ Port 8000 │   │ Port 8000 │   │ Port 8000 │
   └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
                         ▼
             ┌───────────────────────┐
             │     Redis Cache       │
             │  (Session & Rate Lim) │
             └───────────────────────┘
```

- **Nginx:** Đóng vai trò load balancer, reverse proxy, tiếp nhận traffic tại port 80 và phân phối đều tới các agent replica thông qua thuật toán Round Robin.
- **Agent replicas (Stateless):** Chạy code ứng dụng FastAPI, phục vụ truy vấn của người dùng. Các instance không lưu session trong memory cục bộ.
- **Redis:** Lưu trữ conversation history theo `session_id`, rate limit sliding windows và quota token budget của người dùng.

---

## Part 3: Cloud Deployment

### Exercise 3.1 & 3.2: Railway and Render Deployment

- **Public URL:** `https://day12-agent-production.up.railway.app` (hoặc Render Web Service URL)
- **Deployment Platform:** Railway / Render

#### So sánh cấu hình `railway.toml` vs `render.yaml`:

| Tiêu chí | `railway.toml` | `render.yaml` |
|----------|----------------|---------------|
| **Loại cấu hình** | Cấu hình build & deploy cho Railway CLI | Infrastructure as Code (IaC) Blueprint của Render |
| **Khởi tạo dịch vụ** | Định nghĩa build context, healthcheck path và deploy command | Định nghĩa danh sách các services, region, plan, healthcheck, và biến môi trường |
| **Inject Port** | Tự động qua `$PORT` | Tự động qua `$PORT` |
| **Quản lý Secrets** | `railway variables set KEY=VAL` | Khai báo `generateValue: true` hoặc `sync: false` trong YAML |

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication Tests

```bash
# 1. Gọi không kèm API Key -> 401 Unauthorized
curl -i -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'

# HTTP/1.1 401 Unauthorized
# {"detail": "Invalid or missing API key. Include header: X-API-Key: <key>"}

# 2. Gọi với sai API Key -> 401 Unauthorized
curl -i -X POST http://localhost:8000/ask \
  -H "X-API-Key: wrong-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'

# HTTP/1.1 401 Unauthorized
# {"detail": "Invalid or missing API key. Include header: X-API-Key: <key>"}

# 3. Gọi với API Key hợp lệ -> 200 OK
curl -i -X POST http://localhost:8000/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is cloud deployment?"}'

# HTTP/1.1 200 OK
# {
#   "question": "What is cloud deployment?",
#   "answer": "Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được.",
#   "session_id": "...",
#   "model": "gpt-4o-mini",
#   "timestamp": "2026-09-28T03:20:00Z"
# }
```

---

### Exercise 4.2: JWT Authentication (Advanced)

```bash
# 1. Lấy token qua /token endpoint
curl -X POST http://localhost:8000/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "secret"}'

# Response:
# {"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...", "token_type": "bearer"}
```

---

### Exercise 4.3: Rate Limiting Tests (Sliding Window)

Khi người dùng gửi liên tiếp vượt quá 20 requests trong vòng 60 giây:

```bash
# Vượt rate limit sau 20 requests:
# HTTP/1.1 429 Too Many Requests
# Retry-After: 60
# X-RateLimit-Limit: 20
# X-RateLimit-Remaining: 0
# {"detail": "Rate limit exceeded: 20 req/min"}
```

---

### Exercise 4.4: Cost Guard Implementation Approach

- **Cơ chế hoạt động:**
  1. **Tính toán chi phí token:** Dựa trên số từ đầu vào/đầu ra, ước tính token count và tính chi phí dựa trên bảng giá ($0.00015 / 1k input tokens, $0.0006 / 1k output tokens).
  2. **Kiểm tra trước khi gọi LLM:** Hàm `cost_guard.check_budget(user_id, estimated_cost)` kiểm tra tổng chi tiêu trong ngày của user và hệ thống. Nếu tổng chi tiêu vượt hạn mức ngày (`daily_budget_usd = 5.0`), API lập tức trả về mã lỗi `402 Payment Required` để bảo vệ tài khoản khỏi bị cạn kiệt ngân sách ngoài ý muốn.
  3. **Lưu trữ trạng thái phân tán:** Mức chi tiêu được lưu trữ theo key `budget:{user_id}:{YYYY-MM-DD}` trên Redis kèm TTL 2 ngày (có fallback in-memory nếu Redis offline).

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health Checks (Liveness vs Readiness)

- **Liveness Probe (`GET /health`):**
  - Mục đích: Xác nhận process agent vẫn đang hoạt động.
  - Phản hồi: HTTP 200 kèm uptime, tổng số requests, version, môi trường. Nếu server bị deadlock hoặc crash, endpoint không phản hồi và container platform sẽ tiến hành restart container.
- **Readiness Probe (`GET /ready`):**
  - Mục đích: Xác nhận agent đã sẵn sàng nhận traffic (đã kết nối Redis, đã nạp model, không trong tiến trình shutdown).
  - Phản hồi: HTTP 200 nếu sẵn sàng; HTTP 503 nếu Redis mất kết nối hoặc server đang chuẩn bị tắt. Load balancer căn cứ vào đây để ngắt điều hướng traffic tới instance chưa sẵn sàng.

---

### Exercise 5.2: Graceful Shutdown

- Ứng dụng đăng ký signal handler cho `SIGTERM` và `SIGINT`.
- Khi platform gửi `SIGTERM` để scale down hoặc update phiên bản:
  1. Cờ `_is_ready` chuyển thành `False` -> Endpoint `/ready` trả về 503 để Load Balancer ngừng cấp request mới.
  2. Uvicorn cho phép các request đang xử lý dở dang (in-flight requests) hoàn thành trong khoảng thời gian chờ `timeout_graceful_shutdown=30s`.
  3. Đóng các connection pool (Redis, DB) an toàn và kết thúc process mà không làm người dùng gặp lỗi 502/504.

---

### Exercise 5.3 & 5.5: Stateless Design with Redis

- **Vấn đề của Stateful:** Khi scale thành 3 instances, nếu lưu session trong RAM cục bộ của từng instance, câu hỏi tiếp theo của người dùng được Nginx route tới instance khác sẽ bị mất toàn bộ ngữ cảnh hội thoại.
- **Giải pháp:** Mọi hội thoại được serialize thành JSON và lưu trong Redis với key `session:{session_id}`. Bất kỳ instance nào nhận request cũng đều có thể đọc/ghi lịch sử hội thoại của session đó.
- **Kiểm nghiệm (`test_stateless.py`):**
  - Gửi Turn 1 qua load balancer tới `agent_1`.
  - Kill hoặc stop `agent_1`.
  - Gửi Turn 2 qua load balancer tới `agent_2` kèm cùng `session_id`.
  - Kết quả: `agent_2` tải đầy đủ lịch sử từ Redis và trả lời mạch lạc theo đúng ngữ cảnh hội thoại.

---

## Part 6: Final Project Summary

Đã hoàn thành toàn bộ hệ thống tại thư mục `06-lab-complete/`:
- Kiến trúc microservice hoàn chỉnh gồm: `app/main.py`, `app/config.py`, `app/auth.py`, `app/rate_limiter.py`, `app/cost_guard.py`, `utils/mock_llm.py`.
- Dockerfile Multi-stage tối ưu với user `agent` không có quyền root, tích hợp lệnh `HEALTHCHECK`.
- File `docker-compose.yml` định nghĩa stack gồm Agent và Redis Cache.
- Vượt qua 100% (20/20) các tiêu chí kiểm tra của `check_production_ready.py`.
