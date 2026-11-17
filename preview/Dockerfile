# Conteneur d'aperçu avant / après : PHP (pour lancer l'application du dépôt) +
# Chromium sans interface (Playwright), servi par une petite API Python.
# Aucun secret, utilisateur non root, système de fichiers en lecture seule à
# l'exécution (voir docker-compose.yml). Le navigateur ne joint que l'application locale.
FROM composer:2.9 AS composer

FROM php:8.3-cli-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv unzip git ca-certificates libicu-dev libzip-dev \
 && docker-php-ext-install intl zip \
 && rm -rf /var/lib/apt/lists/*

COPY --from=composer /usr/bin/composer /usr/bin/composer

COPY preview/requirements.txt /app/preview/requirements.txt
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r /app/preview/requirements.txt \
 && /opt/venv/bin/playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

COPY checker/__init__.py checker/tools.py /app/checker/
COPY preview/ /app/preview/
RUN useradd --uid 10002 --create-home --shell /usr/sbin/nologin preview \
 && mkdir -p /cache/composer /work && chown -R preview /cache /work

ENV PATH="/opt/venv/bin:${PATH}" \
    HOME=/tmp/home \
    COMPOSER_HOME=/tmp/composer-home \
    COMPOSER_CACHE_DIR=/cache/composer \
    PREVIEW_WORK_DIR=/work \
    TMPDIR=/tmp \
    PYTHONUNBUFFERED=1

WORKDIR /app
USER preview
EXPOSE 8091
CMD ["uvicorn", "preview.app:app", "--host", "0.0.0.0", "--port", "8091"]
