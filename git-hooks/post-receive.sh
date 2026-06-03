#!/bin/bash
# =========================================================
# Git Hook: post-receive (servidor bare)
# Aciona reprocessamento após push recebido
# =========================================================

set -e

# Em hooks bare, o pwd é o repositório bare
REPO_BARE_PATH=$(pwd)
PROJECT_NAME=$(basename "$REPO_BARE_PATH" .git)
COMMIT_HASH=$(git rev-parse HEAD)
COMMIT_MSG=$(git log -1 --pretty=format:"%s")
COMMIT_AUTHOR=$(git log -1 --pretty=format:"%an")

echo "[CodeHelper] 🚀 Hook post-receive acionado"
echo "[CodeHelper]    Projeto: $PROJECT_NAME"
echo "[CodeHelper]    Commit: ${COMMIT_HASH:0:8}"
echo "[CodeHelper]    Autor: $COMMIT_AUTHOR"
echo "[CodeHelper]    Mensagem: $COMMIT_MSG"

# Caminho do reprocessador (ajustar conforme deploy)
REPROCESS_SCRIPT="/opt/codehelper/code_helpe/reprocess.py"
VENV_PATH="/opt/codehelper/env/bin/activate"
LOG_FILE="/opt/codehelper/code_helpe/logs/reprocess_$(date +%Y%m%d_%H%M%S).txt"

mkdir -p "$(dirname "$LOG_FILE")"

if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
fi

if [ -f "$REPROCESS_SCRIPT" ]; then
    echo "[CodeHelper] ⏳ Iniciando pipeline de reprocessamento..."
    python3 "$REPROCESS_SCRIPT" \
        --repo-path "$REPO_BARE_PATH" \
        --project-name "$PROJECT_NAME" \
        --commit-hash "$COMMIT_HASH" \
        --commit-msg "$COMMIT_MSG" \
        >> "$LOG_FILE" 2>&1 && \
        echo "[CodeHelper] ✅ Reprocessamento concluído!" || \
        echo "[CodeHelper] ❌ Falha. Log: $LOG_FILE"
else
    echo "[CodeHelper] ⚠️  Script não encontrado: $REPROCESS_SCRIPT"
fi

exit 0
