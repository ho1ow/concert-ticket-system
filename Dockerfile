FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Cài dependency trước để tận dụng layer cache khi chỉ sửa code.
COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN pip install -r requirements.txt && \
    if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; fi

COPY app ./app
COPY scripts ./scripts
COPY tests ./tests
COPY pyproject.toml .importlinter ./

EXPOSE 8000

# Pha 1 giữ 1 process uvicorn làm baseline cho benchmark.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
