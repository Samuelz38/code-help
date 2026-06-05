#!/bin/bash
# =========================================================
# Git Hook: post-commit (client-side)
# Aciona o pipeline de reprocessamento após cada commit local
# =========================================================

set -euo pipefail

REPO_PATH=$(git rev-parse --show-toplevel)
PROJECT_NAME=$(basename "$REPO_PATH")
COMMIT_HASH=$(git rev-parse HEAD)
COMMIT_MSG=$(git log -1 --pretty=format:"%s")
MARKER_FILE="/tmp/codehelper_reprocess_${PROJECT_NAME}"

# Verifica se há marcação de reprocessamento pendente
if [ ! -f "$MARKER_FILE" ]; then
    exit 0
fi

rm -f "$MARKER_FILE"

echo "[CodeHelper] 🔄 Reprocessando embeddings após commit ${COMMIT_HASH:0:8}..."
echo "[CodeHelper]    Projeto: $PROJECT_NAME"
echo "[CodeHelper]    Mensagem: $COMMIT_MSG"
echo "[CodeHelper]    Início: $(date '+%Y-%m-%d %H:%M:%S')"

if ! command -v docker >/dev/null 2>&1; then
    echo "[CodeHelper] ⚠️  Docker não encontrado no host. Não será possível executar o reprocessamento no container Docker."
    exit 0
fi

cd "$REPO_PATH"

DOCKER_ARGS=(python /app/reprocess.py --repo-path "/repo" --project-name "$PROJECT_NAME" --commit-hash "$COMMIT_HASH" --commit-msg "$COMMIT_MSG")

if docker compose ps -q reprocessor >/dev/null 2>&1 && [ -n "$(docker compose ps -q reprocessor)" ]; then
    echo "[CodeHelper] ▶️ Usando container em execução: reprocessor"
    docker compose exec reprocessor "${DOCKER_ARGS[@]}"
else
    echo "[CodeHelper] ▶️ Container reprocessor não está em execução. Iniciando com docker compose run --rm..."
    docker compose run --rm reprocessor "${DOCKER_ARGS[@]}"
fi

EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    echo "[CodeHelper] ✅ Embeddings atualizados com sucesso!"
else
    echo "[CodeHelper] ❌ Falha no reprocessamento dentro do container. Código de saída: $EXIT_CODE"
fi

exit "$EXIT_CODE"
