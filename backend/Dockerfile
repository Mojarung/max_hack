# Один образ для api, bot, worker и mcp: процесс выбирается командой в compose.yaml.
FROM python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Сначала только зависимости: слой кэшируется, пока не меняется uv.lock.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# platform-api2.max.ru подписан российским корневым CA: httpx берёт certifi, а не системное хранилище.
COPY russian_trusted_root_ca.crt /usr/local/share/ca-certificates/russian_trusted_root_ca.crt
RUN cat /usr/local/share/ca-certificates/russian_trusted_root_ca.crt >> "$(python -c 'import certifi; print(certifi.where())')"

RUN useradd --create-home --uid 10001 domovoy
USER domovoy

EXPOSE 8000 8765
CMD ["domovoy", "api"]
