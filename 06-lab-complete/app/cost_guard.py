"""
Cost Guard Module — LLM Budget Protection

Mục tiêu: Ngăn chặn vượt ngân sách LLM token.
- Tính toán chi phí dựa trên số lượng token input/output
- Kiểm tra ngân sách trước khi gọi LLM
- Lưu trữ mức chi tiêu trong Redis (hoặc fallback in-memory)
"""
import time
import logging
from dataclasses import dataclass, field
from fastapi import HTTPException
from app.config import settings

logger = logging.getLogger(__name__)

# Giá token tham khảo ($ / 1k tokens)
PRICE_PER_1K_INPUT_TOKENS = 0.00015
PRICE_PER_1K_OUTPUT_TOKENS = 0.0006

# Optional Redis connection
_redis_client = None
if settings.redis_url:
    try:
        import redis
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        _redis_client.ping()
    except Exception:
        _redis_client = None


class CostGuard:
    def __init__(self, daily_budget_usd: float = 5.0):
        self.daily_budget_usd = daily_budget_usd
        self._in_memory_costs: dict[str, float] = {}

    def _get_day_key(self, user_id: str) -> str:
        today = time.strftime("%Y-%m-%d")
        return f"budget:{user_id}:{today}"

    def get_current_cost(self, user_id: str = "global") -> float:
        day_key = self._get_day_key(user_id)
        if _redis_client:
            try:
                val = _redis_client.get(day_key)
                return float(val) if val else 0.0
            except Exception:
                pass
        return self._in_memory_costs.get(day_key, 0.0)

    def check_budget(self, user_id: str = "global", estimated_cost: float = 0.0):
        """
        Kiểm tra ngân sách. Raise 402 hoặc 503 nếu vượt hạn mức.
        """
        current_cost = self.get_current_cost(user_id)
        if current_cost + estimated_cost >= self.daily_budget_usd:
            raise HTTPException(
                status_code=402,
                detail=f"Daily budget exhausted: ${current_cost:.4f} / ${self.daily_budget_usd:.2f}. Try tomorrow.",
            )

    def record_cost(self, input_tokens: int, output_tokens: int, user_id: str = "global") -> float:
        """
        Ghi nhận chi phí token đã sử dụng.
        """
        cost = (input_tokens / 1000) * PRICE_PER_1K_INPUT_TOKENS + (output_tokens / 1000) * PRICE_PER_1K_OUTPUT_TOKENS
        day_key = self._get_day_key(user_id)

        if _redis_client:
            try:
                _redis_client.incrbyfloat(day_key, cost)
                _redis_client.expire(day_key, 86400 * 2)  # 2 days TTL
            except Exception as e:
                logger.warning(f"Failed to record cost in Redis: {e}")

        # Update in-memory as well
        self._in_memory_costs[day_key] = self._in_memory_costs.get(day_key, 0.0) + cost
        return cost


cost_guard = CostGuard(daily_budget_usd=settings.daily_budget_usd)


def check_and_record_cost(input_tokens: int, output_tokens: int, user_id: str = "global"):
    cost = (input_tokens / 1000) * PRICE_PER_1K_INPUT_TOKENS + (output_tokens / 1000) * PRICE_PER_1K_OUTPUT_TOKENS
    cost_guard.check_budget(user_id, estimated_cost=cost)
    cost_guard.record_cost(input_tokens, output_tokens, user_id)
