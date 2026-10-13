 FastAPI + SQLAlchemy + PostgreSQL
app/
├── api/                 # FastAPI routers, schema Pydantic
│   ├── deps.py          # get_current_user, require_role — xác thực tập trung
│   └── routers/
├── domain/              # THUẦN Python — không import FastAPI / SQLAlchemy
│   ├── entities.py      # dataclass thực thể
│   ├── errors.py        # lỗi nghiệp vụ
│   └── ports.py         # interface repository (ABC / Protocol)
├── services/            # use case — nhận repository qua constructor
├── infra/
│   ├── db/              # SQLAlchemy models + repository implementations
│   ├── security.py      # hash mật khẩu, ký/verify JWT
│   └── ...
├── main.py              # wiring / dependency injection
tests/
benchmark/               # locust scripts, seed.py, notebook Kaggle
Dockerfile
docker-compose.yml
openapi.yaml
README.md


Nguyên tắc:
Phụ thuộc một chiều: api → services → domain ← infra.
Tầng service chỉ biết interface trong domain/ports.py, nên test unit được bằng fake repository mà không cần DB.
Xác thực JWT đặt ở một dependency/middleware (deps.py). Router chỉ khai báo Depends(get_current_user) hoặc require_role("ADMIN"), không viết lặp trong từng endpoint.
Swagger/OpenAPI tự sinh tại /docs, xuất thêm openapi.yaml vào repo.
