"""Tạo tài khoản ADMIN hoặc STAFF. Không có endpoint nào làm việc này.

    python scripts/create_user.py admin@example.com 'secret123' ADMIN
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.api.deps import get_auth_service  # noqa: E402
from app.domain.auth import Role  # noqa: E402
from app.domain.errors import EmailExists  # noqa: E402
from app.infra.db.session import init_schema  # noqa: E402


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    email, password, role = sys.argv[1], sys.argv[2], sys.argv[3].upper()

    init_schema()
    try:
        user = get_auth_service().create_user(email, password, Role(role))
    except EmailExists:
        print(f"Email đã tồn tại: {email}")
        return 1
    except ValueError:
        print(f"Role không hợp lệ: {role} (USER | STAFF | ADMIN)")
        return 2
    print(f"Đã tạo user #{user.id} {user.email} role={user.role.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
