FROM debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3 AS renderer

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        cmake g++ make zlib1g-dev qt6-base-dev \
        qt6-qpa-plugins qt6-image-formats-plugins fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY renderer ./renderer
RUN cmake -S renderer -B out -DCMAKE_BUILD_TYPE=Release \
    && cmake --build out --parallel \
    && QT_QPA_PLATFORM=offscreen out/terento-preview-render \
        --img renderer/tests/fixture/synthetic-gmapsupp.img \
        --bbox 1.52,42.50,1.544,42.524 --zoom 14-14 --jobs 2 --out /tmp/smoke \
    && test -n "$(find /tmp/smoke -name '*.webp' -print -quit)"

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    QT_QPA_PLATFORM=offscreen \
    TERENTO_PREVIEW_RENDERER=/usr/local/bin/terento-preview-render

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libqt6core6 libqt6gui6 libqt6concurrent6 \
        qt6-qpa-plugins qt6-image-formats-plugins fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=renderer /build/out/terento-preview-render /usr/local/bin/terento-preview-render

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && useradd --system --uid 10001 --no-create-home terento \
    && mkdir -p /var/lib/terento/assets /var/lib/terento/preview-work \
    && chown -R terento:terento /var/lib/terento

USER terento
EXPOSE 8000

CMD ["terento-catalog-api"]
