# Stage 1: Build frontend
FROM node:24-slim AS frontend
WORKDIR /build
RUN corepack enable && corepack prepare pnpm@latest --activate
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

# Stage 2: Python runtime
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Copy built frontend
COPY --from=frontend /build/dist ./static/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
