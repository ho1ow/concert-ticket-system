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

Khán giả chọn concert, xem sơ đồ ghế, giữ 1 đến 4 ghế trong 10 phút, tạo đơn
PENDING, thanh toán, nhận vé QR. Ở mọi bước trước khi thanh toán, nếu hết 10 phút
hoặc người dùng chủ động nhả thì ghế về AVAILABLE.

### 2.1 Ban tổ chức dựng một concert

Tạo địa điểm, sinh ghế hàng loạt theo dải, tạo concert ở trạng thái DRAFT, chia
khu vực kèm giá và danh sách ghế, rồi mở bán.

Bước mở bán chạy trong một transaction: kiểm tra event đang DRAFT, có ít nhất một
khu vực, mọi ghế đã được gán khu vực, rồi sinh bản ghi ghế cho event ở trạng thái
AVAILABLE và chuyển event sang PUBLISHED. Ghế chưa gán khu vực thì trả 409.

### 2.2 Giữ ghế

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

### 2.3 Tạo đơn

Hold phải thuộc chính user, đang ACTIVE và còn hạn, nếu không trả 410
HOLD_EXPIRED. Tổng tiền tính theo giá khu vực tại thời điểm tạo đơn và lưu vào
từng dòng của đơn. Đơn nhận luôn `expires_at` của hold. Ràng buộc unique trên
`hold_id` khiến một hold chỉ sinh được một đơn.

### 2.4 Thanh toán

Thiếu header `Idempotency-Key` thì trả 400. Tra bảng thanh toán theo cặp user và
key: đã có và cùng đơn thì trả lại đúng response cũ; đã có nhưng khác đơn thì trả
422 IDEMPOTENCY_KEY_REUSED.

Đơn phải PENDING, thuộc chính user, còn hạn. Quá hạn thì chuyển đơn sang EXPIRED
và trả 410.

Transaction chốt gồm: chuyển đơn PENDING sang PAID có điều kiện, chuyển ghế HELD
sang SOLD chỉ cho ghế còn đúng `hold_id` này, sinh vé với mã QR ngẫu nhiên, lưu
bản ghi thanh toán. Nếu số ghế chuyển sang SOLD nhỏ hơn số ghế của đơn, nghĩa là
hold đã hết hạn và người khác kịp lấy ghế, thì rollback và trả 409.

### 2.5 Soát vé

Check-in cập nhật `checked_in_at` với điều kiện cột này đang rỗng. Không cập nhật
được dòng nào nghĩa là vé đã dùng rồi, trả 409 ALREADY_CHECKED_IN kèm thời điểm
check-in trước đó.

## 3. Kiến trúc

### 3.1 Phân tầng

    api/       router và schema
    services/  xử lý logic nghiệp vụ
    domain/    thực thể, lỗi nghiệp vụ, và interface repository
    infra/     giao tiếp với PostgreSQL

api → services → domain ← infra

## 4. Ma trận phân quyền

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

## 5. Triển khai

### 5.1 Deploy

Cần Docker và Docker Compose
    docker compose up -d --build

Compose dựng hai service: `db` là PostgreSQL 16 và `api` là ứng dụng. Service `api`
chỉ khởi động sau khi `db` báo healthy, bảng được tạo tự động ở lần đầu.

| Thành phần | Địa chỉ |
|---|---|
| API | http://localhost:8000 |
| Đặc tả API | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| PostgreSQL | `localhost:5433`, user, mật khẩu và tên database đều là `concert` |

Cổng 5433 để không đụng PostgreSQL có sẵn trên máy. Thư mục `app` được mount và
uvicorn chạy `--reload`, nên sửa code không cần build lại image.

### 5.2 Tài khoản quản trị

API không cho đăng ký ADMIN hay STAFF. Dùng `make seed` để tạo tài khoản mẫu, hoặc
tạo thủ công:

    docker compose exec api python scripts/create_user.py admin@example.com adminpass123 ADMIN
