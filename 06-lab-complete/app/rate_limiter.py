"""
Rate Limiting Module — Sliding Window Counter

Supports:
- Redis-based sliding window if Redis is available and configured
- In-memory deque sliding window fallback
- Configurable requests per window
"""
import time
from collections import defaultdict, deque
from fastapi import HTTPException
from app.config import settings

# Optional Redis connection
_redis_client = None
if settings.redis_url:
    try:
        import redis
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        _redis_client.ping()
    except Exception:
        _redis_client = None


class RateLimiter:
    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._in_memory_windows: dict[str, deque] = defaultdict(deque)

    def check(self, key: str):
        """
        Check if request limit exceeded for key.
        Raises HTTPException(429) if exceeded.
        """
        now = time.time()

        if _redis_client:
            try:
                redis_key = f"ratelimit:{key}"
                pipe = _redis_client.pipeline()
                # Remove timestamps older than window
                pipe.zremrangebyscore(redis_key, 0, now - self.window_seconds)
                # Count current requests in window
                pipe.zcard(redis_key)
                # Add current timestamp
                pipe.zadd(redis_key, {str(now): now})
                # Set TTL
                pipe.expire(redis_key, self.window_seconds + 5)
                _, current_count, _, _ = pipe.execute()

                if current_count >= self.max_requests:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded: {self.max_requests} req/min",
                        headers={"Retry-After": str(self.window_seconds)},
                    )
                return
            except HTTPException:
                raise
            except Exception:
                # Fallback to in-memory on Redis error
                pass

        # In-memory sliding window
        window = self._in_memory_windows[key]
        while window and window[0] < now - self.window_seconds:
            window.popleft()

        if len(window) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.max_requests} req/min",
                headers={"Retry-After": str(self.window_seconds)},
            )
        window.append(now)


# Default rate limiter singleton
rate_limiter = RateLimiter(
    max_requests=settings.rate_limit_per_minute,
    window_seconds=60,
)


def check_rate_limit(key: str = "default"):
    rate_limiter.check(key)
