# Concert Ticket System

Dịch vụ backend đặt vé concert. Đồ án môn Software Architecture.

Stack: FastAPI, SQLAlchemy, PostgreSQL. Chạy bằng `docker compose up -d --build`,
đặc tả API xem ở http://localhost:8000/docs.

## 1. Yêu cầu nghiệp vụ

### 1.1 Các bên tham gia

| Vai trò | Phạm vi |
|---|---|
| USER (khán giả) | Xem concert và sơ đồ ghế, giữ ghế tạm, tạo đơn, thanh toán, nhận vé QR |
| STAFF (soát vé) | Check-in vé tại cửa |
| ADMIN (ban tổ chức) | Tạo địa điểm và ghế, tạo concert, chia khu vực và giá, mở bán |

ADMIN có mọi quyền của STAFF. STAFF và ADMIN vẫn mua vé được như USER. Tài khoản
STAFF và ADMIN không tạo được qua API, chỉ bằng script CLI.

### 1.2 Quy tắc nghiệp vụ

| # | Quy tắc |
|---|---|
| R1 | Chỉ giữ được ghế khi event đang PUBLISHED và đã đến `sale_open_at` |
| R2 | Một lần giữ chỉ gồm ghế của một event, từ 1 đến 4 ghế |
| R3 | Tối đa 4 ghế mỗi user mỗi event, tính cả hold còn hạn và vé đã mua |
| R4 | Hold hết hạn sau 10 phút; tạo đơn và thanh toán đều phải kiểm tra hold còn hạn |
| R5 | Một ghế thuộc tối đa một hold đang hiệu lực hoặc một vé |
| R6 | Số vé bán ra của mỗi event không vượt quá số ghế |
| R7 | Giữ ghế theo nguyên tắc tất cả hoặc không, không giữ được một phần |
| R8 | Thanh toán idempotent: cùng `Idempotency-Key` trả lại kết quả cũ |
| R9 | Giá chốt tại thời điểm tạo đơn, không đọc lại giá lúc thanh toán |
| R10 | Một vé chỉ check-in được một lần |
| R11 | Mỗi ghế của event thuộc đúng một khu vực, khu vực quyết định giá |

### 1.3 Vòng đời đối tượng

| Đối tượng | Trạng thái |
|---|---|
| Event | DRAFT → PUBLISHED → CANCELLED |
| Ghế của event | AVAILABLE → HELD → SOLD. HELD về lại AVAILABLE khi hết hạn hoặc bị nhả |
| Hold | ACTIVE → CONVERTED (đã tạo đơn) / RELEASED (tự nhả) / EXPIRED |
| Order | PENDING → PAID / CANCELLED / EXPIRED |
| Ticket | chưa check-in → đã check-in (`checked_in_at` có giá trị) |

## 2. Workflow nghiệp vụ

### 2.1 Ban tổ chức dựng một concert

Tạo địa điểm, sinh ghế hàng loạt theo dải, tạo concert ở trạng thái DRAFT, chia
khu vực kèm giá và danh sách ghế, rồi mở bán.

Bước mở bán chạy trong một transaction: kiểm tra event đang DRAFT, có ít nhất một
khu vực, mọi ghế của địa điểm đã được gán khu vực; sinh bản ghi ghế cho event với
trạng thái AVAILABLE; chuyển event sang PUBLISHED. Còn ghế chưa gán khu vực thì
trả 409.

Ghế vật lý của địa điểm và ghế của một suất diễn là hai bảng riêng, nên một địa
điểm tổ chức nhiều concert mà trạng thái ghế không lẫn vào nhau.

### 2.2 Khán giả mua vé

Chọn concert, xem sơ đồ ghế, giữ 1 đến 4 ghế trong 10 phút, tạo đơn PENDING,
thanh toán, nhận vé QR. Ở mọi bước trước khi thanh toán, nếu hết 10 phút hoặc
người dùng chủ động nhả thì ghế về AVAILABLE.

### 2.3 Giữ ghế

Đây là phần tranh chấp nặng nhất, vì hàng nghìn người cùng nhắm một khu ghế trong
vài giây đầu mở bán.

1. Kiểm tra số ghế trong khoảng 1 đến 4 và không có id trùng nhau.
2. Event phải PUBLISHED và đã đến giờ mở bán, nếu không trả 409 SALE_NOT_OPEN.
3. Mở transaction, khoá theo cặp user và event.
4. Đếm số ghế user đang giữ cộng số vé đã mua, vượt 4 thì trả 422 LIMIT_EXCEEDED.
5. Tạo hold ACTIVE hết hạn sau 10 phút.
6. Chiếm ghế bằng một câu UPDATE có điều kiện, chỉ thành công với ghế đang trống
   hoặc đã hết hạn giữ.
7. Số dòng cập nhật nhỏ hơn số ghế yêu cầu thì rollback toàn bộ và trả 409
   SEAT_UNAVAILABLE kèm danh sách ghế đã mất.

Bước 3 cần thiết vì không có khoá thì một user gửi 5 request song song, cả 5 đều
đọc thấy đang giữ 0 ghế và đều lọt qua bước 4, giới hạn 4 ghế mất hiệu lực.

Hold hết hạn được xử lý kiểu lazy: ghế HELD mà `held_until` đã qua được coi là
trống, không cần job nền dọn dẹp.

### 2.4 Tạo đơn

Hold phải thuộc chính user, đang ACTIVE và còn hạn, nếu không trả 410
HOLD_EXPIRED. Tổng tiền tính theo giá khu vực tại thời điểm tạo đơn và lưu vào
từng dòng của đơn. Đơn nhận luôn `expires_at` của hold. Ràng buộc unique trên
`hold_id` khiến một hold chỉ sinh được một đơn.

### 2.5 Thanh toán

Thiếu header `Idempotency-Key` thì trả 400. Tra bảng thanh toán theo cặp user và
key: đã có và cùng đơn thì trả lại đúng response cũ; đã có nhưng khác đơn thì trả
422 IDEMPOTENCY_KEY_REUSED.

Đơn phải PENDING, thuộc chính user, còn hạn. Quá hạn thì chuyển đơn sang EXPIRED
và trả 410. Gọi cổng thanh toán xong mới mở transaction, vì không gọi I/O bên
ngoài trong lúc đang giữ transaction.

Transaction chốt gồm: chuyển đơn PENDING sang PAID có điều kiện, chuyển ghế HELD
sang SOLD chỉ cho ghế còn đúng `hold_id` này, sinh vé với mã QR ngẫu nhiên, lưu
bản ghi thanh toán. Nếu số ghế chuyển sang SOLD nhỏ hơn số ghế của đơn, nghĩa là
hold đã hết hạn và người khác kịp lấy ghế, thì rollback và trả 409.

Điều kiện `hold_id` ở câu lệnh trên là lý do cách xử lý hết hạn kiểu lazy vẫn an
toàn: ghế đã bị người khác giữ lại sẽ mang `hold_id` khác, câu lệnh không cập nhật
được dòng nào.

Webhook của cổng thanh toán dùng chung logic chốt đơn, nhưng xác thực bằng HMAC
trên raw body kèm chống replay thay vì dùng JWT.

### 2.6 Soát vé

Check-in cập nhật `checked_in_at` với điều kiện cột này đang rỗng. Không cập nhật
được dòng nào nghĩa là vé đã dùng rồi, trả 409 ALREADY_CHECKED_IN kèm thời điểm
check-in trước đó.

## 3. Ma trận phân quyền

| Endpoint | Public | USER | STAFF | ADMIN | Kiểm tra thêm ở tầng service |
|---|:--:|:--:|:--:|:--:|---|
| `POST /auth/register`, `/login`, `/refresh` | x | | | | |
| `GET /auth/me` | | x | x | x | |
| `GET /venues`, `/venues/{id}`, `/venues/{id}/seats` | x | | | | |
| `POST /venues`, `/venues/{id}/seats` | | | | x | |
| `GET /events`, `/events/{id}`, `/zones`, `/seats` | x | | | | Public chỉ thấy PUBLISHED, ADMIN thấy cả DRAFT |
| `POST` `PUT` `DELETE /events`, `/publish`, `POST /zones` | | | | x | Kiểm tra trạng thái DRAFT |
| `POST /holds` | | x | x | x | Giới hạn 4 ghế, thời gian mở bán |
| `GET` `DELETE /holds/{id}` | | x | x | x | Chủ sở hữu |
| `POST /orders` | | x | x | x | Hold phải của mình |
| `GET /orders/me`, `GET /tickets/me` | | x | x | x | Lọc theo user lấy từ token |
| `GET /orders/{id}` | | x | x | x | Chủ sở hữu hoặc ADMIN |
| `DELETE /orders/{id}`, `POST /orders/{id}/pay` | | x | x | x | Chủ sở hữu, ADMIN không trả tiền hộ |
| `POST /payments/webhook` | HMAC | | | | Chữ ký, timestamp, chống replay |
| `POST /tickets/{code}/check-in` | | | x | x | Vé chưa check-in, đúng event |

Quyền được kiểm ở ba chỗ: middleware xác thực token, dependency theo role gắn ở
cấp nhóm router, và kiểm tra quyền sở hữu tài nguyên trong tầng service. Tài
nguyên của người khác trả 404 chứ không phải 403, để không tiết lộ id nào đang tồn
tại.

## 4. Triển khai

### 4.1 Yêu cầu

Docker và Docker Compose. Không cần cài Python hay PostgreSQL trên máy.

### 4.2 Chạy

    docker compose up -d --build

Compose dựng hai service: `db` là PostgreSQL 16 và `api` là ứng dụng. Service
`api` chỉ khởi động sau khi `db` báo healthy. Bảng được tạo tự động ở lần khởi
động đầu.

| Thành phần | Địa chỉ |
|---|---|
| API | http://localhost:8000 |
| Đặc tả API | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| PostgreSQL | `localhost:5433`, user, mật khẩu và tên database đều là `concert` |

Cổng 5433 được chọn để không đụng PostgreSQL có sẵn trên máy. Thư mục `app` được
mount vào container và uvicorn chạy với `--reload`, nên sửa code không cần build
lại image.

### 4.3 Tạo tài khoản quản trị

API không cho đăng ký ADMIN hay STAFF. Dùng script trong container:

    docker compose exec api python scripts/create_user.py admin@example.com adminpass123 ADMIN
    docker compose exec api python scripts/create_user.py staff@example.com staffpass123 STAFF

### 4.4 Các lệnh thường dùng

Makefile gói lại các lệnh hay dùng:

| Lệnh | Tác dụng |
|---|---|
| `make up` | Build và bật toàn bộ hệ thống |
| `make down` | Tắt và xoá luôn volume dữ liệu |
| `make logs` | Xem log của service api |
| `make sh` | Mở shell trong container api |
| `make psql` | Mở psql vào database |
| `make test` | Chạy pytest trong container |
| `make lint` | Kiểm tra ràng buộc phụ thuộc giữa các tầng bằng import-linter |
| `make openapi` | Sinh lại `openapi.yaml` và `openapi.json` |
| `make seed` | Tạo tài khoản ADMIN và STAFF mẫu |

### 4.5 Cấu hình

Toàn bộ cấu hình đọc từ biến môi trường, mẫu đầy đủ ở `.env.example`. Trong
compose, các biến cần thiết đã được đặt sẵn cho môi trường phát triển.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DATABASE_URL` | trỏ tới service `db` | Chuỗi kết nối, chấp nhận cả `sqlite://` để test nhanh |
| `JWT_SECRET` | `dev-secret-change-me` | Khoá ký access token |
| `WEBHOOK_SECRET` | `dev-webhook-secret` | Khoá HMAC cho webhook thanh toán |
| `ACCESS_TOKEN_TTL_SECONDS` | 900 | Thời hạn access token |
| `REFRESH_TOKEN_TTL_DAYS` | 7 | Thời hạn refresh token |
| `LOGIN_LOCK_THRESHOLD` | 5 | Số lần sai mật khẩu thì khoá tài khoản |
| `LOGIN_LOCK_MINUTES` | 15 | Thời gian khoá |
| `HOLD_TTL_MINUTES` | 10 | Thời gian giữ ghế, quy tắc R4 |
| `MAX_SEATS_PER_USER_PER_EVENT` | 4 | Quy tắc R3 |
| `DB_POOL_SIZE` | 10 | Kích thước connection pool |
| `DB_LOCK_TIMEOUT_MS` | 2000 | Thời gian chờ khoá tối đa của một câu lệnh |
| `DB_STATEMENT_TIMEOUT_MS` | 5000 | Thời gian chạy tối đa của một câu lệnh |
| `AUTO_CREATE_SCHEMA` | true | Tạo bảng khi khởi động |
| `HOLD_STRATEGY` | atomic | `naive` chỉ dùng khi benchmark để chứng minh lỗi bán trùng |

### 4.6 Khi deploy thật

Những điểm phải đổi so với cấu hình phát triển:

- Đặt `JWT_SECRET` và `WEBHOOK_SECRET` bằng giá trị ngẫu nhiên, truyền qua biến
  môi trường hoặc secret manager, không commit vào repo.
- Đổi mật khẩu PostgreSQL và không publish cổng 5433 ra ngoài.
- Bỏ phần mount thư mục `app` và bỏ `--reload` trong lệnh chạy, để container
  dùng đúng code đã build trong image.
- Đặt `AUTO_CREATE_SCHEMA=false` và quản lý schema bằng migration nếu hệ thống
  đã có dữ liệu thật.
- Chạy sau một reverse proxy có TLS, vì access token đi trong header.

Pha 1 cố ý giữ một process uvicorn và PostgreSQL thuần để làm mốc đo. Các hướng
mở rộng của Pha 2 gồm nhiều worker gunicorn sau Nginx, PgBouncer cho connection
pool, Redis cho việc giữ ghế và cache sơ đồ ghế, rate limit cho endpoint giữ ghế.

### 4.7 Chạy không dùng Docker

Cần Python 3.12 và PostgreSQL đang chạy.

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements-dev.txt
    export DATABASE_URL="postgresql+psycopg://concert:concert@localhost:5432/concert"
    uvicorn app.main:app --reload
