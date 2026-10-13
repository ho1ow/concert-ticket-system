"""4 endpoint xác thực. Không có dòng nào kiểm tra quyền ở đây."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, CurrentActor
from app.api.errors import error_responses
from app.api.schemas import LoginIn, MeOut, RefreshIn, RegisterIn, TokenOut, UserOut

public_router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(prefix="/auth", tags=["auth"])


@public_router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản",
    description=(
        "Role luôn là USER. Mọi field lạ (kể cả `role`) bị từ chối 422, nên "
        "không thể mass-assign quyền ADMIN. Không trả token, client phải "
        "gọi `/auth/login` riêng."
    ),
    responses=error_responses(409, 422),
)
def register(payload: RegisterIn, service: AuthServiceDep) -> UserOut:
    user = service.register(email=payload.email, password=payload.password)
    return UserOut.from_entity(user)


@public_router.post(
    "/login",
    response_model=TokenOut,
    summary="Đăng nhập",
    description=(
        "Sai email và sai mật khẩu trả về cùng một thông báo 401. Sai 5 lần "
        "liên tiếp thì tài khoản bị khoá 15 phút."
    ),
    responses=error_responses(401, 422),
)
def login(payload: LoginIn, service: AuthServiceDep) -> TokenOut:
    pair = service.login(email=payload.email, password=payload.password)
    return TokenOut(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
    )


@public_router.post(
    "/refresh",
    response_model=TokenOut,
    summary="Xoay vòng refresh token",
    description=(
        "Refresh token dùng một lần: gọi thành công thì token cũ bị thu hồi "
        "ngay. Dùng lại một token đã thu hồi được coi là dấu hiệu bị đánh "
        "cắp, toàn bộ family bị thu hồi và phiên đăng nhập kết thúc."
    ),
    responses=error_responses(401, 422),
)
def refresh(payload: RefreshIn, service: AuthServiceDep) -> TokenOut:
    pair = service.refresh(payload.refresh_token)
    return TokenOut(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
    )


@me_router.get(
    "/me",
    response_model=MeOut,
    summary="Thông tin tài khoản đang đăng nhập",
    responses=error_responses(401, 404),
)
def me(actor: CurrentActor, service: AuthServiceDep) -> MeOut:
    return MeOut.from_entity(service.me(actor))
