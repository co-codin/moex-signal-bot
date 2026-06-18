FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MOEX_SIGNAL_DB=/data/signals.sqlite3

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 appuser && mkdir -p /data && chown appuser:appuser /data
USER appuser

VOLUME ["/data"]

CMD ["python", "-m", "moex_signal_bot"]
