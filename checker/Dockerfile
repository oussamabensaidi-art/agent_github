# Conteneur de contrôles statiques : PHP + Composer + PHPStan + PHP-CS-Fixer + gitleaks,
# servi par une petite API Python. Aucun secret, utilisateur non root, système de
# fichiers en lecture seule à l'exécution (voir docker-compose.yml).
FROM composer:2.9 AS composer

FROM php:8.3-cli-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv unzip git ca-certificates curl libicu-dev libzip-dev \
 && docker-php-ext-install intl zip \
 && rm -rf /var/lib/apt/lists/*

COPY --from=composer /usr/bin/composer /usr/bin/composer

# Outils PHP, versions figées.
RUN mkdir -p /opt/tools \
 && cd /opt/tools \
 && COMPOSER_HOME=/tmp/composer composer require --no-interaction --no-progress \
      phpstan/phpstan:2.3.5 friendsofphp/php-cs-fixer:3.95.30 \
 && rm -rf /tmp/composer

# gitleaks, version figée, somme de contrôle vérifiée.
ARG GITLEAKS_VERSION=8.30.1
RUN cd /tmp \
 && curl -fsSLO "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
 && curl -fsSLO "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_checksums.txt" \
 && grep " gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz$" "gitleaks_${GITLEAKS_VERSION}_checksums.txt" | sha256sum -c - \
 && tar -xzf "gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" gitleaks \
 && install -m 0755 gitleaks /usr/local/bin/gitleaks \
 && rm -f /tmp/gitleaks*

COPY checker/requirements.txt /app/checker/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /app/checker/requirements.txt

COPY checker/ /app/checker/
RUN mkdir -p /opt/checker && cp /app/checker/phpstan.neon /app/checker/cs.php /opt/checker/ \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin checker  && mkdir -p /cache/composer /work && chown -R checker /cache /work

ENV PATH="/opt/venv/bin:${PATH}" \
    HOME=/home/checker \
    COMPOSER_HOME=/tmp/composer-home \
    COMPOSER_CACHE_DIR=/cache/composer \
    CHECKER_WORK_DIR=/work \
    TMPDIR=/tmp \
    PYTHONUNBUFFERED=1

WORKDIR /app
USER checker
EXPOSE 8090
CMD ["uvicorn", "checker.app:app", "--host", "0.0.0.0", "--port", "8090"]
