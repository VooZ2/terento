FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && useradd --system --uid 10001 --no-create-home terento \
    && mkdir -p /var/lib/terento/assets \
    && chown -R terento:terento /var/lib/terento

USER terento
EXPOSE 8000

CMD ["terento-catalog-api"]
