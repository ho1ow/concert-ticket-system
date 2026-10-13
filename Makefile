.PHONY: up down logs sh test openapi lint seed psql rebuild

up:            ## Bật API + Postgres (http://localhost:8000/docs)
	docker compose up -d --build
	@echo "Swagger UI: http://localhost:8000/docs"

down:          ## Tắt và xoá volume dữ liệu
	docker compose down -v

logs:
	docker compose logs -f api

sh:
	docker compose exec api bash

test:          ## Chạy pytest trong container
	docker compose run --rm --no-deps api pytest -q

openapi:       ## Sinh openapi.yaml + openapi.json
	docker compose run --rm --no-deps -v "$(PWD)":/out api \
		sh -c "python scripts/export_openapi.py && cp openapi.yaml openapi.json /out/"

lint:          ## Kiểm tra ràng buộc phụ thuộc giữa các tầng
	docker compose run --rm --no-deps api lint-imports

seed:          ## Tạo tài khoản admin/staff mẫu
	docker compose exec api python scripts/create_user.py admin@example.com adminpass123 ADMIN
	docker compose exec api python scripts/create_user.py staff@example.com staffpass123 STAFF

psql:
	docker compose exec db psql -U concert -d concert

rebuild:
	docker compose build --no-cache
