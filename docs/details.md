1. Luồng tổng thể
Admin:  POST /venues → POST /venues/{id}/seats → POST /events (DRAFT)
        → POST /events/{id}/zones → POST /events/{id}/publish (PUBLISHED, sinh event_seats)

Khán giả: GET /events → GET /events/{id}/seats
          → POST /holds (ghế HELD, hold ACTIVE, 10 phút)
          → POST /orders (order PENDING)
          → POST /orders/{id}/pay (order PAID, ghế SOLD, sinh tickets)
          → GET /tickets/me

Staff:  POST /tickets/{code}/check-in

Vòng đời của các đối tượng:

Đối tượng	Trạng thái
Event	DRAFT → PUBLISHED → CANCELLED
Ghế (event_seat)	AVAILABLE → HELD → SOLD; HELD về lại AVAILABLE khi hết hạn hoặc bị nhả
Hold	ACTIVE → CONVERTED (đã tạo đơn) / RELEASED (tự nhả) / EXPIRED
Order	PENDING → PAID / CANCELLED / EXPIRED
Ticket	chưa check-in → đã check-in (checked_in_at có giá trị)
2. Luồng nghiệp vụ từng API
Auth
API	Điều kiện / xử lý	Lỗi
POST /auth/register	Kiểm tra định dạng email, mật khẩu ≥ 8 ký tự, hash argon2; role mặc định USER	409 email đã tồn tại, 422 dữ liệu sai
POST /auth/login	Tìm user, verify hash, trả access token (30 phút) và refresh token (7 ngày)	401 với cùng một thông báo cho sai email và sai mật khẩu
POST /auth/refresh	Chỉ nhận token có typ=refresh còn hạn, trả access token mới	401
GET /auth/me	Trả thông tin user lấy từ token	401
Địa điểm (Admin)
API	Điều kiện / xử lý	Lỗi
POST /venues	Tạo venue	422
POST /venues/{id}/seats	Body [{section, row, from, to}], sinh ghế hàng loạt; UNIQUE(venue_id, section, row, number)	404 venue, 409 trùng ghế
GET /venues, GET /venues/{id}	Phân trang ?page=&size= (size tối đa 100)	404
Concert
API	Điều kiện / xử lý	Lỗi
POST /events	Tạo ở trạng thái DRAFT, phải có start_time > sale_open_at > now	422
PUT /events/{id}	Chỉ sửa được khi DRAFT. Khi đã PUBLISHED chỉ cho sửa title/mô tả	409 sai trạng thái
DELETE /events/{id}	Chỉ khi DRAFT	409
POST /events/{id}/publish	Điều kiện: DRAFT, có ít nhất 1 zone, mọi ghế của venue đã được gán zone. Trong một transaction: sinh event_seats (status AVAILABLE) cho tất cả ghế, rồi chuyển event sang PUBLISHED	409 sai trạng thái hoặc còn ghế chưa gán zone
GET /events?status=&from=&to=	Public, chỉ trả event PUBLISHED (admin xem được tất cả), phân trang	
GET /events/{id}	Kèm thông tin zone và giá	404
Khu vực & ghế
API	Điều kiện / xử lý	Lỗi
POST /events/{id}/zones	Chỉ khi DRAFT. Body {name, price, seat_ids[]}; mỗi ghế thuộc tối đa 1 zone	409 ghế đã thuộc zone khác
GET /events/{id}/zones	Kèm số ghế còn trống của mỗi zone	
GET /events/{id}/seats?zone=	Trả [{event_seat_id, section, row, number, zone, price, status}]. Ghế HELD có held_until < now được trả về là AVAILABLE (lazy expiry)	404
Giữ ghế (lõi tranh chấp)

POST /holds với body {event_id, seat_ids[]}:

Validate: 1 ≤ số ghế ≤ 4, không có id trùng nhau.
Event phải PUBLISHED và now >= sale_open_at, nếu không trả 409 SALE_NOT_OPEN.
Mở transaction, khoá theo cặp (user, event) để một user không gửi song song nhiều request lách giới hạn (xem mục 3).
Đếm số ghế user đang giữ (hold ACTIVE còn hạn) cộng số vé đã mua. Nếu cộng thêm số ghế mới mà vượt 4 thì trả 422 LIMIT_EXCEEDED.
Tạo hold ACTIVE, expires_at = now + 10 phút.
Chiếm ghế bằng một câu UPDATE có điều kiện, chỉ thành công nếu ghế đang trống hoặc đã hết hạn giữ.
Nếu số dòng cập nhật nhỏ hơn số ghế yêu cầu thì rollback toàn bộ và trả 409 SEAT_UNAVAILABLE, kèm danh sách ghế bị mất. Nguyên tắc tất cả hoặc không: không bao giờ giữ được một phần.
Commit, trả 201 {hold_id, seat_ids, expires_at}.
API	Điều kiện / xử lý	Lỗi
GET /holds/{id}	Chỉ chủ hold được xem; trả seconds_left	404 (dùng 404 thay 403 để không lộ id tồn tại)
DELETE /holds/{id}	Chủ hold và hold đang ACTIVE. Nhả ghế HELD → AVAILABLE với điều kiện hold_id khớp, hold chuyển RELEASED	404, 409 hold đã thành đơn
Đơn hàng

POST /orders với body {hold_id}:

Hold phải thuộc user, đang ACTIVE và expires_at > now. Nếu không: 410 HOLD_EXPIRED hoặc 404.
Tính tổng tiền theo giá zone tại thời điểm tạo đơn và lưu vào order_items.price (không đọc lại giá lúc thanh toán).
Tạo order PENDING (expires_at = expires_at của hold), chuyển hold sang CONVERTED. Ràng buộc UNIQUE(hold_id) để một hold chỉ sinh một đơn.
Trả 201 {order_id, total, expires_at}.
API	Điều kiện / xử lý	Lỗi
GET /orders/me	Phân trang, mới nhất trước	
GET /orders/{id}	Chỉ chủ đơn hoặc admin	404
DELETE /orders/{id}	Chỉ khi PENDING. Đơn chuyển CANCELLED, ghế HELD → AVAILABLE theo hold_id	409 đơn đã thanh toán
Thanh toán

POST /orders/{id}/pay với header Idempotency-Key:

Thiếu header thì trả 400.
Tra bảng payments theo (user_id, idempotency_key):
Đã có và cùng order_id: trả lại đúng response cũ, không xử lý lại.
Đã có nhưng khác order_id: trả 422 IDEMPOTENCY_KEY_REUSED.
Order phải PENDING, thuộc user, expires_at > now. Nếu đã quá hạn: chuyển order sang EXPIRED và trả 410.
Gọi cổng thanh toán giả lập (Pha 1 luôn thành công, hoặc có tham số để mô phỏng thất bại).
Một transaction gồm: chuyển order PENDING → PAID (có điều kiện), chuyển ghế HELD → SOLD chỉ cho ghế còn đúng hold_id này, sinh tickets với mã QR ngẫu nhiên 128-bit, lưu payment kèm response.
Nếu số ghế chuyển sang SOLD nhỏ hơn số ghế của đơn (ví dụ hold đã hết hạn và người khác lấy mất ghế) thì rollback, đánh dấu payment FAILED/REFUND và trả 409.

POST /payments/webhook (callback của cổng thanh toán):

Verify chữ ký X-Signature = HMAC-SHA256(secret, timestamp + body) bằng phép so sánh thời gian hằng (hmac.compare_digest). Lệch giờ quá 5 phút thì từ chối, chống replay.
UNIQUE(provider_ref): nhận lại cùng một callback thì trả 200 mà không xử lý lại.
Phần cập nhật trạng thái dùng chung logic với bước 5 ở trên.
Vé
API	Điều kiện / xử lý	Lỗi
GET /tickets/me	Danh sách vé kèm thông tin event và ghế	
POST /tickets/{code}/check-in	Role STAFF. Cập nhật checked_in_at = now() với điều kiện checked_in_at IS NULL; 0 dòng cập nhật nghĩa là đã check-in rồi. Event phải còn hiệu lực	404 mã sai, 409 ALREADY_CHECKED_IN (kèm thời điểm check-in trước)
3. Điều kiện để hàng nghìn người đặt cùng lúc vẫn đúng

Nguyên tắc chung: không tin vào bước “kiểm tra rồi mới ghi” ở tầng ứng dụng. Mọi bất biến phải được chính database bảo vệ, bằng một câu lệnh nguyên tử hoặc một ràng buộc.

3.1 Bất biến và cơ chế bảo vệ
Bất biến	Cơ chế đảm bảo	Ghi chú
Một ghế chỉ thuộc 1 hold đang hiệu lực	UPDATE có điều kiện + kiểm tra số dòng (bên dưới)	Đây là chốt chặn chính
Một ghế chỉ có 1 vé	UNIQUE(event_seat_id) trên tickets	Lưới an toàn thứ hai nếu code có bug
Tối đa 4 ghế/user/event	Khoá theo cặp (user, event): pg_advisory_xact_lock(user_id, event_id)	Không khoá thì một user gửi 5 request song song, mỗi request đều thấy “mới giữ 0 ghế”
Một hold chỉ sinh 1 đơn	UNIQUE(hold_id) trên orders	
Thanh toán không lặp	UNIQUE(user_id, idempotency_key), UNIQUE(provider_ref)	
Đơn chỉ chuyển sang PAID một lần	UPDATE orders SET status='PAID' WHERE id=:id AND status='PENDING'	
Vé chỉ check-in một lần	UPDATE ... WHERE checked_in_at IS NULL	

Câu lệnh giữ ghế (dùng cho cả Pha 1):

sql
UPDATE event_seats
SET status = 'HELD', hold_id = :hold_id, held_until = now() + interval '10 minutes'
WHERE event_id = :event_id
  AND id = ANY(:seat_ids)
  AND (status = 'AVAILABLE' OR (status = 'HELD' AND held_until < now()))
RETURNING id;
-- len(RETURNING) < len(seat_ids)  →  ROLLBACK + 409

Câu lệnh chốt bán khi thanh toán:

sql
UPDATE event_seats SET status = 'SOLD'
WHERE hold_id = :hold_id AND status = 'HELD' AND held_until >= now()
RETURNING id;

Nhờ điều kiện hold_id = :hold_id, nếu hold đã hết hạn và người khác kịp giữ lại ghế (ghế lúc đó mang hold_id mới) thì câu này không cập nhật được dòng nào. Như vậy lazy expiry vẫn an toàn.

3.2 Quy tắc viết transaction
Sắp xếp seat_ids tăng dần trước khi UPDATE. Hai request khoá cùng nhóm ghế theo thứ tự khác nhau sẽ gây deadlock.
Dùng một nguồn thời gian duy nhất: now() của database, không dùng giờ của từng worker Python (các worker có thể lệch giờ nhau).
Transaction ngắn, không gọi I/O bên ngoài bên trong transaction. Gọi cổng thanh toán xong mới mở transaction để chốt.
Mức cô lập READ COMMITTED mặc định của Postgres là đủ, vì tính đúng nằm ở các UPDATE có điều kiện và ràng buộc UNIQUE, không cần SERIALIZABLE.
Gặp xung đột thì trả 409 ngay, server không tự retry. Client tự chọn ghế khác.
Đặt lock_timeout (khoảng 2 giây) và statement_timeout (khoảng 5 giây) để request bị kẹt không giữ connection mãi.
3.3 Điều kiện về hiệu năng
Hạng mục	Pha 1 (bắt buộc, chi phí thấp)	Pha 2 (cải tiến, đo trước/sau)
Index	event_seats(event_id, zone_id), event_seats(hold_id), holds(user_id, event_id, status), orders(user_id, created_at), tickets(code) UNIQUE	
Truy vấn	Sơ đồ ghế lấy bằng 1 câu JOIN, tránh N+1; danh sách luôn phân trang	Cache-aside sơ đồ ghế bằng Redis
Connection pool	SQLAlchemy pool_size khoảng 10–20, pool_timeout ngắn	PgBouncer khi chạy nhiều worker
Worker	1 process uvicorn (giữ làm baseline)	gunicorn nhiều worker + Nginx
Chống spam		Rate limit POST /holds theo user/IP, waiting room khi mở bán
Giữ ghế	Trên Postgres (UPDATE có điều kiện)	Redis SET NX EX + Lua, DB chỉ ghi khi thanh toán
Hết hạn hold	Lazy	Job nền dọn hold, hoặc Redis TTL

Một lưu ý cho câu chuyện Pha 2: làm đúng như trên thì Pha 1 đã không còn double-booking, nên “trước cải tiến” sẽ không còn lỗi đúng đắn để demo. Có hai cách xử lý:

(a) Giữ Pha 1 đúng, Pha 2 tập trung vào hiệu năng. Nghẽn ở DB khi hàng nghìn người tranh cùng một khu ghế làm p95 cao và nhiều timeout; Pha 2 giải bằng Redis, cache và scale. Cách này an toàn hơn.
(b) Có thêm một cờ cấu hình HOLD_STRATEGY=naive|atomic. Bản naive dùng kiểu kiểm tra rồi mới ghi, chỉ để benchmark chứng minh double-booking; mặc định chạy bản atomic. Cách này có thêm một bảng số liệu “số ghế bán trùng: X → 0” rất thuyết phục.

Mình khuyên dùng (b): chi phí chỉ vài chục dòng code, mà có cả số liệu về tính đúng lẫn số liệu về hiệu năng.

3.4 Bảng mã lỗi thống nhất

Mọi lỗi trả về dạng {"error": "<CODE>", "message": "..."}:

HTTP	Code	Khi nào
400	MISSING_IDEMPOTENCY_KEY	Gọi /pay thiếu header
401	UNAUTHORIZED	Thiếu token, token sai hoặc hết hạn
403	FORBIDDEN	Sai role
404	NOT_FOUND	Không tồn tại, hoặc không phải của mình
409	SEAT_UNAVAILABLE, SALE_NOT_OPEN, INVALID_STATE, ALREADY_CHECKED_IN	Xung đột trạng thái
410	HOLD_EXPIRED, ORDER_EXPIRED	Quá hạn 10 phút
422	LIMIT_EXCEEDED, IDEMPOTENCY_KEY_REUSED, lỗi validate	Vi phạm quy tắc nghiệp vụ
429	RATE_LIMITED	Pha 2