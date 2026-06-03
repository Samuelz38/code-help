#!/bin/bash
# =========================================================
# Git Hook: pre-push
# Verifica se há commits no remoto que não estão no branch local antes de dar push.
# =========================================================

set -e

REPO_PATH=$(git rev-parse --show-toplevel)
PROJECT_NAME=$(basename "$REPO_PATH")
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)
REMOTE_NAME=origin

if [ -n "$CURRENT_BRANCH" ] && git remote | grep -q "^$REMOTE_NAME$"; then
    if git fetch --quiet "$REMOTE_NAME" "$CURRENT_BRANCH" >/dev/null 2>&1; then
        REMOTE_AHEAD=$(git rev-list --count "HEAD..$REMOTE_NAME/$CURRENT_BRANCH" 2>/dev/null || echo 0)

        if [ "$REMOTE_AHEAD" -gt 0 ]; then
            echo "[CodeHelper] ⚠️  O remoto '$REMOTE_NAME/$CURRENT_BRANCH' está $REMOTE_AHEAD commit(s) à frente do seu branch local."
            echo "[CodeHelper]    Faça git pull antes de dar push para evitar conflitos e garantir que você esteja na versão mais recente."
            exit 1
        fi
    else
        echo "[CodeHelper] ℹ️  Não foi possível verificar o remoto '$REMOTE_NAME'. Continuando sem checar a versão remota."
    fi
fi

exit 0
