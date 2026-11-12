# --- Étape 1 : interface de suivi (Vite + React), tout est embarqué : aucun CDN ---
FROM node:22-alpine AS ui
WORKDIR /ui
COPY ui/frontend/package.json ui/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/frontend/ ./
RUN npm run build

# --- Étape 2 : agent (API webhook + interface, ou worker) ---
FROM python:3.12-slim

WORKDIR /app

# LangSmith (embarqué par LangGraph) : traçage cloud coupé — aucun code ne sort de l'infra.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING_V2=false

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=ui /dist ./ui/dist

# Utilisateur non-root ; /data reçoit le journal d'audit.
RUN useradd --create-home --uid 10001 bot && mkdir -p /data && chown bot /data
USER bot

EXPOSE 8020

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020"]
