1. Vai trò và ma trận quyền

Hệ thống có 3 vai trò: USER (khán giả), STAFF (soát vé), ADMIN (ban tổ chức). ADMIN có quyền của STAFF; STAFF và ADMIN đều có thể mua vé như USER.

Endpoint	Public	USER	STAFF	ADMIN	Kiểm tra ở service
POST /auth/register, /login, /refresh	✅				
GET /auth/me		✅	✅	✅	
GET /venues, /venues/{id}	✅				
POST /venues, /venues/{id}/seats				✅	
GET /events, /events/{id}, /zones, /seats	✅				Public chỉ thấy PUBLISHED; ADMIN thấy cả DRAFT
POST/PUT/DELETE /events, /publish, POST /zones				✅	Kiểm tra trạng thái DRAFT
POST /holds		✅	✅	✅	Giới hạn 4 ghế, thời gian mở bán
GET/DELETE /holds/{id}		✅	✅	✅	Chủ sở hữu
POST /orders		✅	✅	✅	Hold phải của mình
GET /orders/me		✅	✅	✅	Lọc theo user_id từ token
GET /orders/{id}		✅	✅	✅	Chủ sở hữu, hoặc ADMIN
DELETE /orders/{id}, POST /orders/{id}/pay		✅	✅	✅	Chủ sở hữu (ADMIN cũng không được trả tiền hộ)
POST /payments/webhook	Không dùng JWT, xác thực bằng HMAC				Chữ ký, timestamp, chống replay
GET /tickets/me		✅	✅	✅	Lọc theo user_id
POST /tickets/{code}/check-in			✅	✅	Chưa check-in, đúng event

Nên đưa nguyên bảng này vào README. Nó vừa là đặc tả, vừa là checklist để test.

2. Authentication
2.1 Thiết kế token
	Access token	Refresh token
Định dạng	JWT HS256	Chuỗi ngẫu nhiên 256-bit (opaque, không phải JWT)
Thời hạn	15 phút	7 ngày
Lưu ở server	Không lưu (stateless)	Lưu hash SHA-256 trong bảng refresh_tokens
Gửi kèm	Authorization: Bearer ...	Body của POST /auth/refresh
Thu hồi được không	Không, tự hết hạn sau 15 phút	Có

Claims của access token:

json
{ "sub": "42", "role": "USER", "typ": "access",
  "iat": 1760000000, "exp": 1760000900, "iss": "concert-api", "jti": "..." }

Không đưa email hay thông tin cá nhân vào token, vì payload JWT chỉ được mã hoá base64, ai cũng đọc được.

Bảng hỗ trợ:

refresh_tokens(id, user_id, token_hash UNIQUE, family_id, expires_at, revoked_at, replaced_by, created_at)
users(..., role, is_active, failed_logins, locked_until)
2.2 Luồng register
Pydantic validate với extra="forbid": email đúng định dạng, mật khẩu từ 8 đến 72 ký tự.
Bỏ qua mọi trường role trong body. Role luôn là USER (chống mass assignment). Tài khoản ADMIN và STAFF chỉ được tạo bằng script seed hoặc CLI.
Chuẩn hoá email (strip().lower()), hash mật khẩu bằng argon2.
Insert. Ràng buộc UNIQUE(email) do DB chặn, nên hai request đăng ký cùng email song song không thể cùng thành công.
Trả 201 {id, email}. Không trả token, client phải login riêng.
2.3 Luồng login
Tìm user theo email.
Không tìm thấy user: vẫn chạy verify với một hash giả để thời gian phản hồi bằng trường hợp có user, tránh dò email qua timing. Trả 401 INVALID_CREDENTIALS.
User đang bị khoá (locked_until > now): trả 401 với cùng thông báo, không tiết lộ là tài khoản bị khoá.
Sai mật khẩu: failed_logins += 1. Đủ 5 lần thì locked_until = now + 15 phút. Trả 401 cùng thông báo.
Đúng mật khẩu: reset failed_logins, phát access token, tạo refresh token mới (bắt đầu một family_id mới), lưu hash của nó.
Trả {access_token, refresh_token, token_type: "bearer", expires_in: 900}.
2.4 Luồng refresh, có xoay vòng (rotation) và phát hiện tái sử dụng
Client gửi refresh token R1
  ├─ hash(R1) không có trong DB, hoặc đã hết hạn       → 401
  ├─ R1 đã bị thu hồi (revoked_at != null)             → TÁI SỬ DỤNG: có thể bị đánh cắp
  │                                                       → thu hồi CẢ family, 401
  └─ hợp lệ → thu hồi R1, phát R2 cùng family, phát access token mới

Vì token đã dùng thì bị thu hồi ngay, nếu kẻ tấn công lấy được R1 và dùng nó sau khi người dùng thật đã refresh (hoặc ngược lại), lần dùng thứ hai sẽ bị phát hiện và cả phiên đăng nhập bị huỷ. Thao tác thu hồi R1 phải là UPDATE có điều kiện WHERE revoked_at IS NULL để hai request refresh song song không cùng thành công. Đây cũng chính là kỹ thuật dùng cho ghế.

2.5 Kiểm tra access token ở mỗi request (get_current_user)
Không có header Authorization: Bearer: trả 401 kèm WWW-Authenticate: Bearer.
jwt.decode với algorithms=["HS256"] cố định, bắt buộc có các claim exp, sub, typ, iss. Cách này chặn alg: none và nhầm thuật toán.
typ phải là access, để không dùng nhầm token loại khác.
Trả về Actor(id, role). Không query DB ở bước này, giữ hot path nhanh khi tải cao.

Đánh đổi của bước 4: user bị khoá hoặc đổi role vẫn dùng được access token cũ tối đa 15 phút. Với đồ án như vậy là chấp nhận được. Nếu muốn thu hồi ngay, thêm cột token_version vào users, đưa vào claim và so khớp (tốn thêm 1 query, hoặc đọc cache ở Pha 2).

3. Authorization
3.1 Lớp 2: role ở cấp router (main.py)
python
public    = APIRouter()
protected = APIRouter(dependencies=[Depends(get_current_user)])
staff     = APIRouter(dependencies=[Depends(require_role("STAFF", "ADMIN"))])
admin     = APIRouter(dependencies=[Depends(require_role("ADMIN"))])

public.include_router(auth.public_router)       # register, login, refresh
public.include_router(venues.read_router)
public.include_router(events.read_router)
protected.include_router(auth.me_router)
protected.include_router(holds.router)
protected.include_router(orders.router)
protected.include_router(tickets.me_router)
staff.include_router(tickets.checkin_router)
admin.include_router(venues.write_router)
admin.include_router(events.write_router)

for r in (public, protected, staff, admin):
    app.include_router(r)
app.include_router(payments.webhook_router)     # tự xác thực bằng HMAC

Mỗi module tách router đọc và router ghi, rồi gắn vào nhóm quyền tương ứng. Trong file router không có dòng nào kiểm tra quyền.

3.2 Lớp 3: quyền trên tài nguyên ở service

Tầng service không được import FastAPI, nên định nghĩa Actor và policy trong domain/:

python
# domain/auth.py — thuần Python
from dataclasses import dataclass
from enum import Enum

class Role(str, Enum):
    USER = "USER"; STAFF = "STAFF"; ADMIN = "ADMIN"

@dataclass(frozen=True)
class Actor:
    id: int
    role: Role
    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

def ensure_owner(actor: Actor, owner_id: int, *, admin_can_read: bool = False) -> None:
    if actor.id == owner_id:
        return
    if admin_can_read and actor.is_admin:
        return
    raise NotFound()          # 404 thay vì 403: không xác nhận tài nguyên tồn tại
python
# services/order_service.py
class OrderService:
    def get(self, actor: Actor, order_id: int) -> Order:
        with self._uow() as uow:
            order = uow.orders.get(order_id)
            if order is None:
                raise NotFound()
            ensure_owner(actor, order.user_id, admin_can_read=True)
            return order

    def pay(self, actor: Actor, order_id: int, idem_key: str) -> Payment:
        with self._uow() as uow:
            order = uow.orders.get(order_id)
            if order is None:
                raise NotFound()
            ensure_owner(actor, order.user_id)            # admin cũng không trả hộ
            if order.status != OrderStatus.PENDING:
                raise InvalidState("Order is not pending")
            ...

Router chỉ chuyển Actor từ dependency xuống service:

python
@router.get("/orders/{order_id}")
def get_order(order_id: int, actor: CurrentActor):
    return OrderOut.from_entity(order_service.get(actor, order_id))

Quy tắc chung:

Các endpoint /me lấy user_id từ token, không bao giờ nhận user_id từ query hay body.
POST /orders {hold_id}: kiểm tra hold là của actor. Không có bước này, user A có thể tạo đơn từ hold của user B.
Trả 404 cho tài nguyên của người khác, để không lộ id nào đang tồn tại.
ID dạng số tăng dần dễ đoán. Mã QR của vé nhất định phải ngẫu nhiên (secrets.token_urlsafe(16)). ID đơn hàng có thể giữ kiểu số vì đã có kiểm tra quyền sở hữu.
3.3 Webhook: xác thực giữa hai máy, không dùng JWT
python
def verify_webhook(body: bytes, ts: str, sig: str) -> None:
    if abs(time.time() - int(ts)) > 300:
        raise Unauthorized("stale")                                   # chống replay theo thời gian
    expected = hmac.new(SECRET, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):                        # so sánh thời gian hằng
        raise Unauthorized("bad signature")

Phải verify trên raw body (await request.body()), trước khi parse JSON. Kết hợp thêm UNIQUE(provider_ref) để chặn replay trong khoảng 5 phút cho phép.

4. Bảng mã lỗi xác thực
HTTP	Code	Trường hợp
401	UNAUTHORIZED	Thiếu token, token sai hoặc hết hạn, sai typ
401	INVALID_CREDENTIALS	Sai email, sai mật khẩu, hoặc tài khoản bị khoá (cùng một thông báo)
401	INVALID_REFRESH_TOKEN	Refresh token sai, hết hạn hoặc bị tái sử dụng
403	FORBIDDEN	Đúng người nhưng sai role
404	NOT_FOUND	Tài nguyên không tồn tại hoặc không phải của mình
409	EMAIL_EXISTS	Đăng ký trùng email

Đăng ký trùng email trả 409 sẽ cho phép dò email đã đăng ký. Với đồ án thì chấp nhận được; nếu muốn chặt hơn, luôn trả 202 và gửi email xác nhận.

5. Bố trí file
domain/auth.py            Role, Actor, ensure_owner             (thuần Python)
domain/ports.py           PasswordHasher, TokenIssuer, RefreshTokenRepository
services/auth_service.py  register, login, refresh               (gọi qua ports)
infra/security.py         Argon2Hasher, JwtTokenService          (pwdlib, PyJWT)
infra/db/repositories.py  SqlUserRepository, SqlRefreshTokenRepository
api/deps.py               get_current_user, require_role, CurrentActor
api/routers/auth.py       4 endpoint auth
main.py                   chia router theo nhóm quyền

import-linter sẽ xác nhận services/ và domain/ không import jwt, pwdlib, fastapi.

6. Test bắt buộc cho phần auth
Nhóm	Ca kiểm thử
AuthN	Không token → 401; token hết hạn → 401; token ký bằng secret khác → 401; token alg: none → 401; dùng refresh token làm access token → 401
Login	Sai mật khẩu và email không tồn tại trả cùng thông báo; sai 5 lần → bị khoá
Refresh	Refresh thành công thì token cũ không dùng lại được; dùng lại token cũ → cả family bị thu hồi
Role	USER gọi endpoint admin → 403; USER gọi check-in → 403; STAFF check-in được
IDOR	User B gọi GET/DELETE /holds/{id}, GET /orders/{id}, POST /orders/{id}/pay, POST /orders {hold_id} trên tài nguyên của user A → 404
Mass assignment	Register với "role": "ADMIN" → tài khoản vẫn là USER
Webhook	Sai chữ ký → 401; timestamp cũ → 401; gửi lại cùng provider_ref → 200 nhưng không xử lý lại

Ca IDOR nên viết thành test tham số hoá, chạy qua mọi endpoint có {id}. Khi thêm endpoint mới mà quên ensure_owner, CI sẽ báo đỏ.