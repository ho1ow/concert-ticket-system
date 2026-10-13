Đặt vé concert 
Khán giả: xem concert và sơ đồ ghế, giữ ghế tạm, thanh toán, nhận vé QR.
Ban tổ chức (admin): tạo địa điểm và ghế, tạo concert, chia khu vực và giá, mở bán, xem thống kê.
Nhân viên soát vé (staff): check-in vé.
Xem concert → Xem ghế → Giữ ghế (HOLD, TTL 10 phút) → Tạo đơn → Thanh toán → Nhận vé
                              └─ hết TTL / huỷ → ghế về AVAILABLE

Trạng thái ghế
AVAILABLE ──hold──▶ HELD ──pay──▶ SOLD
    ▲                 │
    └──expire/release─┘
Một ghế chỉ thuộc tối đa một hold ACTIVE hoặc một vé.
Số vé bán ra của mỗi event không vượt số ghế.
Mỗi user giữ hoặc mua tối đa 4 ghế cho mỗi event

Quy tắc nghiệp vụ
Chỉ giữ ghế khi event đang PUBLISHED và now >= sale_open_at.
Một lần giữ chỉ gồm ghế của một event; tối đa 4 ghế/user/event (tính cả hold active và vé đã mua).
Hold hết hạn sau 10 phút; POST /orders và /pay phải kiểm tra hold còn hạn.
Thanh toán idempotent: cùng Idempotency-Key trả lại kết quả cũ.
Pha 1 xử lý hết hạn kiểu lazy: coi HELD có held_until < now là AVAILABLE


Nhóm
Method
Path
Ghi chú
Auth
POST
/auth/register




POST
/auth/login
trả JWT


POST
/auth/refresh




GET
/auth/me
[Auth]
Địa điểm
GET
/venues




GET
/venues/{id}




POST
/venues
[Admin]


POST
/venues/{id}/seats
[Admin] tạo ghế hàng loạt
Concert
GET
/events?status=&from=&to=
hot đọc


GET
/events/{id}




POST
/events
[Admin]


PUT
/events/{id}
[Admin]


DELETE
/events/{id}
[Admin] chỉ khi DRAFT


POST
/events/{id}/publish
[Admin] sinh event_seats
Khu vực & ghế
GET
/events/{id}/zones




POST
/events/{id}/zones
[Admin] gán giá + ghế


GET
/events/{id}/seats?zone=
hot nhất về đọc: sơ đồ ghế
Giữ ghế
POST
/holds
[Auth] hot nhất về ghi, body {event_id, seat_ids[]}


GET
/holds/{id}
[Auth] thời gian còn lại


DELETE
/holds/{id}
[Auth] nhả ghế
Đơn hàng
POST
/orders
[Auth] {hold_id}


GET
/orders/me
[Auth]


GET
/orders/{id}
[Auth]


DELETE
/orders/{id}
[Auth] huỷ đơn PENDING
Thanh toán
POST
/orders/{id}/pay
[Auth] header Idempotency-Key


POST
/payments/webhook
callback giả lập, xác thực HMAC
Vé
GET
/tickets/me
[Auth]


POST
/tickets/{code}/check-in
[Staff] chống check-in 2 lần
Thống kê
GET
/admin/events/{id}/stats
[Admin] bán / giữ / trống, doanh thu



