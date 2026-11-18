# Raspberry Pi 4B（linux/arm64）與本機開發共用的 Coordinator 映像
# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STACKCHAN_COORDINATOR_DB=/data/coordinator.sqlite3 \
    STACKCHAN_LISTEN_HOST=0.0.0.0 \
    STACKCHAN_LISTEN_PORT=8443 \
    STACKCHAN_CONTRACTS_DIR=/app/docs/stackchan-agent-spec/contracts

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY docs/stackchan-agent-spec/contracts ./docs/stackchan-agent-spec/contracts

RUN pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 8443

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8443/healthz', timeout=2)"

CMD ["stackchan", "coordinator", "serve-pi"]
