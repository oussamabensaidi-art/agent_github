#!/usr/bin/env bash
# Comparaison des modèles sur les 30 PR du banc (code fictif uniquement).
#   bash bench_real/run_models.sh            # les trois modèles, l'un après l'autre
# Qwen3-14B : API Calipso. Les deux modèles Coder : OpenRouter (data_collection=deny).
set -u
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
PY=.venv/Scripts/python
F="-f docker-compose.yml -f docker-compose.github.yml"
LOCAL_HOSTS="localhost,127.0.0.1,ollama,host.docker.internal,188.40.58.26"

round() {  # tag fournisseur modèle
  local tag=$1
  export BENCH_LLM_PROVIDER=$2 BENCH_OPENROUTER_MODEL=$3
  export BENCH_LLM_ALLOWED_HOSTS="$LOCAL_HOSTS$([ "$2" = openrouter ] && echo ,openrouter.ai)"
  echo "=== $tag : $2 ${3:-qwen3-14b-awq/chat} — $(date +%T)"
  docker compose $F up -d --scale worker=3 >/dev/null 2>&1
  sleep 12
  docker compose $F logs worker --since 20s 2>&1 | grep -m1 "worker prêt" | sed -E 's/^.*worker prêt/  worker prêt/'
  $PY bench_real/run_bench.py prepare --tag "$tag" --suite all >/dev/null 2>&1 || { echo "  préparation en échec"; return 1; }
  $PY bench_real/run_bench.py launch --tag "$tag" --workers 3 2>&1 | tail -1
  $PY bench_real/run_bench.py collect --tag "$tag" --timeout 3000 > "bench_real/results/$tag-collect.log" 2>&1
  mv "bench_real/results/$tag-collect.log" "bench_real/results/$tag/collect.log"
  grep -E "^- (Verdicts|Défauts|PR propres|Durée totale)" "bench_real/results/$tag/report.md"
}

round m14b qwen3api ""
round m30b openrouter qwen/qwen3-coder-30b-a3b-instruct
round mnext openrouter qwen/qwen3-coder-next

# Retour au modèle Calipso.
export BENCH_LLM_PROVIDER=qwen3api BENCH_OPENROUTER_MODEL="" BENCH_LLM_ALLOWED_HOSTS="$LOCAL_HOSTS"
docker compose $F up -d --scale worker=3 >/dev/null 2>&1
echo "=== terminé — $(date +%T)"
