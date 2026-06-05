#!/usr/bin/env bash
set -euo pipefail

echo "🚀 [Entrypoint] Inicializando CodeHelper..."

REPO_PATH="${REPO_PATH:-/repo}"
HOOKS_DIR="${HOOKS_DIR:-/app/git-hooks}"

if [ -d "$REPO_PATH/.git" ]; then
    echo "📁 Repositório encontrado: $REPO_PATH"
    mkdir -p "$REPO_PATH/.git/hooks"

    if compgen -G "$HOOKS_DIR/*.sh" >/dev/null; then
        echo "🔧 Instalando hooks Git em $REPO_PATH..."
        for hook_file in "$HOOKS_DIR"/*.sh; do
            if [ ! -f "$hook_file" ]; then
                continue
            fi

            hook_name=$(basename "$hook_file" .sh)
            if [ "$hook_name" = "install_hooks" ]; then
                continue
            fi

            cp "$hook_file" "$REPO_PATH/.git/hooks/$hook_name"
            chmod +x "$REPO_PATH/.git/hooks/$hook_name"
            echo "   - $hook_name"
        done
        echo "✅ Hooks instalados com sucesso!"
    else
        echo "⚠️  Nenhum hook encontrado em $HOOKS_DIR"
    fi
else
    echo "⚠️  Repositório não encontrado em $REPO_PATH"
    echo "💡 Verifique a variável REPO_PATH no docker-compose ou em .env"
fi

echo "🎯 Executando comando principal..."
exec "$@"
