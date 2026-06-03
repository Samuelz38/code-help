#!/bin/bash
# =========================================================
# Git Hook: pre-commit
# Executado ANTES de cada commit no repositório do projeto
# Função: detectar mudanças nos arquivos de código e marcar para reprocessamento
# =========================================================

set -e

# Verifica se existe versão nova no remoto antes de continuar
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)
if [ -n "$CURRENT_BRANCH" ] && git remote | grep -q '^origin$'; then
    if git fetch --quiet origin "$CURRENT_BRANCH" >/dev/null 2>&1; then
        LOCAL_AHEAD=$(git rev-list --count "origin/$CURRENT_BRANCH..HEAD" 2>/dev/null || echo 0)
        REMOTE_AHEAD=$(git rev-list --count "HEAD..origin/$CURRENT_BRANCH" 2>/dev/null || echo 0)

        if [ "$REMOTE_AHEAD" -gt 0 ]; then
            echo "[CodeHelper] ⚠️  Há $REMOTE_AHEAD commit(s) no remoto origin/$CURRENT_BRANCH que não estão no seu branch local. Faça pull antes de commitar/push."
        elif [ "$LOCAL_AHEAD" -gt 0 ]; then
            echo "[CodeHelper] ℹ️  Seu branch local está $LOCAL_AHEAD commit(s) à frente do remoto origin/$CURRENT_BRANCH."
        fi
    else
        echo "[CodeHelper] ℹ️  Falha ao verificar o remoto origin. Continuando sem checar novas versões remotas."
    fi
fi

REPO_PATH=$(git rev-parse --show-toplevel)
PROJECT_NAME=$(basename "$REPO_PATH")
MARKER_FILE="/tmp/codehelper_reprocess_${PROJECT_NAME}"

# Obtém lista de arquivos modificados (staged)
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(cpp|hpp|h|c|py|js|ts)$' || true)

if [ -z "$STAGED_FILES" ]; then
    echo "[CodeHelper] Nenhum arquivo de código modificado. Pulando marcação."
    exit 0
fi

echo "[CodeHelper] 🔍 Detectadas mudanças em arquivo(s) de código."
echo "$STAGED_FILES" > "$MARKER_FILE"

# Validação rápida de sintaxe
CPP_ERRORS=0
PY_ERRORS=0

for file in $STAGED_FILES; do
    if [[ "$file" =~ \.(cpp|hpp|h|c)$ ]]; then
        if command -v g++ &> /dev/null; then
            if ! g++ -fsyntax-only "$REPO_PATH/$file" 2>/dev/null; then
                echo "[CodeHelper] ⚠️  Possível erro de sintaxe em: $file"
                CPP_ERRORS=$((CPP_ERRORS + 1))
            fi
        fi
    elif [[ "$file" =~ \.py$ ]]; then
        if ! python3 -m py_compile "$REPO_PATH/$file" 2>/dev/null; then
            echo "[CodeHelper] ⚠️  Erro de sintaxe Python em: $file"
            PY_ERRORS=$((PY_ERRORS + 1))
        fi
    fi
done

if [ $CPP_ERRORS -gt 0 ] || [ $PY_ERRORS -gt 0 ]; then
    echo "[CodeHelper] ⚠️  Foram detectados $CPP_ERRORS erro(s) C++ e $PY_ERRORS erro(s) Python."
fi

echo "[CodeHelper] ✅ Repositório marcado para reprocessamento automático após o commit."
exit 0
