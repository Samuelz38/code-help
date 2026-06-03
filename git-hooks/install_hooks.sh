#!/bin/bash
# =========================================================
# Script de instalação dos Git Hooks
# Uso: bash ./git-hooks/install_hooks.sh /caminho/do/repositorio
# =========================================================

set -e

if [ $# -lt 1 ]; then
    echo "Uso: $0 <caminho-do-repositorio>"
    echo "Exemplo: $0 ~/projetos/opencv"
    exit 1
fi

REPO_PATH="$1"
HOOKS_DIR="$REPO_PATH/.git/hooks"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$REPO_PATH/.git" ]; then
    echo "❌ Diretório não é um repositório git: $REPO_PATH"
    exit 1
fi

if [ ! -d "$HOOKS_DIR" ]; then
    echo "❌ Diretório de hooks não encontrado: $HOOKS_DIR"
    exit 1
fi

echo "🔧 Instalando Git Hooks no repositório: $REPO_PATH"

for hook in pre-commit.sh post-commit.sh pre-push.sh post-receive.sh; do
    if [ -f "$SCRIPT_DIR/$hook" ]; then
        cp "$SCRIPT_DIR/$hook" "$HOOKS_DIR/${hook%.sh}"
        chmod +x "$HOOKS_DIR/${hook%.sh}"
        echo "   ✅ ${hook%.sh} instalado"
    fi
done

echo ""
echo "✅ Hooks instalados com sucesso."
echo "📋 Para testar, edite um arquivo de código e execute:" 

echo "   cd $REPO_PATH && git add . && git commit -m 'test: hook'"
echo ""
echo "⚠️  Se usar post-receive, ele deve ser instalado em um repositório bare remoto."
