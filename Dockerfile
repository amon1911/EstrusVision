# syntax=docker/dockerfile:1.7
# =============================================================================
# Stage 1: Builder — ติดตั้ง dependencies ด้วย uv
# =============================================================================
FROM python:3.11-slim-bookworm AS builder

# ติดตั้ง uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# System deps สำหรับ build psycopg2 และ Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# ตั้งค่า uv environment
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Copy lock files ก่อน (ใช้ Docker cache อย่างมีประสิทธิภาพ)
COPY pyproject.toml uv.lock* ./

# Install dependencies (ไม่รวมโค้ดของเรา — ทำให้ cache layer ดี)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source code
COPY . .

# Install โปรเจกต์เอง
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# =============================================================================
# Stage 2: Runtime — image เล็ก ไม่ต้องมี build tools
# =============================================================================
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

# Runtime deps เท่านั้น
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy venv และ source code จาก builder
COPY --from=builder /app /app

# ใช้ venv ของ uv โดยตรง
ENV PATH="/app/.venv/bin:$PATH"

# สร้างโฟลเดอร์ที่จำเป็น
RUN mkdir -p temp_images logs

CMD ["python", "main.py"]