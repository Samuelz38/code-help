#!/bin/bash
# =========================================================
# Git Hook: post-commit (client-side)
# Aciona o pipeline de reprocessamento após cada commit local
# =========================================================

set -e

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

# Resolve caminho do reprocessador (assume estrutura padrão do projeto)
REPROCESS_SCRIPT="${REPO_PATH}/../../reprocess.py"
VENV_PATH="${REPO_PATH}/../../env/bin/activate"
LOG_FILE="${REPO_PATH}/../../logs/reprocess_$(date +%Y%m%d_%H%M%S).txt"

# Cria diretório de logs
mkdir -p "$(dirname "$LOG_FILE")"

if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
fi

if [ -f "$REPROCESS_SCRIPT" ]; then
    echo "[CodeHelper] 🔄 Reprocessando embeddings após commit ${COMMIT_HASH:0:8}..."
    echo "[CodeHelper]    Projeto: $PROJECT_NAME"
    echo "[CodeHelper]    Mensagem: $COMMIT_MSG"
    echo "[CodeHelper]    Início: $(date '+%Y-%m-%d %H:%M:%S')"

    python3 "$REPROCESS_SCRIPT" \
        --repo-path "$REPO_PATH" \
        --project-name "$PROJECT_NAME" \
        --commit-hash "$COMMIT_HASH" \
        --commit-msg "$COMMIT_MSG" \
        >> "$LOG_FILE" 2>&1 && \
        echo "[CodeHelper] ✅ Embeddings atualizados com sucesso!" || \
        echo "[CodeHelper] ❌ Falha no reprocessamento. Verifique: $LOG_FILE"
else
    echo "[CodeHelper] ⚠️  Script de reprocessamento não encontrado: $REPROCESS_SCRIPT"
    echo "[CodeHelper]    Instale o reprocessador em ../../reprocess.py"
fi

exit 0
