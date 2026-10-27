"""Cổng thanh toán giả lập.

Pha 1: luôn trả về thành công, có thể dùng biến môi trường
``PAYMENT_GATEWAY_FAIL=1`` để mô phỏng thất bại khi benchmark.
"""

from __future__ import annotations

import os
import secrets
import time


class FakePaymentGateway:
    def charge(self, *, order_id: int, amount: int) -> dict:
        if os.environ.get("PAYMENT_GATEWAY_FAIL") == "1":
            return {
                "provider_ref": secrets.token_urlsafe(16),
                "status": "FAILED",
                "amount": amount,
                "timestamp": int(time.time()),
                "reason": "simulated_failure",
            }
        return {
            "provider_ref": secrets.token_urlsafe(16),
            "status": "SUCCEEDED",
            "amount": amount,
            "timestamp": int(time.time()),
        }
