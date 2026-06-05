#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

function parse_env() {
    local key="$1"
    local file="$2"
    grep -E "^${key}=" "$file" | tail -n1 | cut -d '=' -f2- | tr -d '"' | xargs || true
}

if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Docker não encontrado. Instale o Docker primeiro."
    exit 1
fi

if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
    echo "❌ Docker Compose não encontrado. Instale o Docker Compose ou use o plugin docker compose."
    exit 1
fi

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "📄 Criando .env a partir de .env.example..."
        cp .env.example .env
    else
        echo "❌ Arquivo .env.example não encontrado."
        exit 1
    fi
fi

REPO_PATH=$(parse_env "REPO_PATH" .env)
PROJECT_NAME=$(parse_env "PROJECT_NAME" .env)
DB_NAME=$(parse_env "DB_NAME" .env)
DB_USER=$(parse_env "DB_USER" .env)
DB_PASSWORD=$(parse_env "DB_PASSWORD" .env)

DB_NAME=${DB_NAME:-codehelper}
DB_USER=${DB_USER:-codehelper}
DB_PASSWORD=${DB_PASSWORD:-codehelper123}

if [ -z "$REPO_PATH" ]; then
    echo "❌ REPO_PATH não está definido em .env. Ajuste o arquivo e execute novamente."
    exit 1
fi

HOST_REPO_PATH="$REPO_PATH"
if [[ "$HOST_REPO_PATH" != /* ]]; then
    HOST_REPO_PATH="$ROOT_DIR/$HOST_REPO_PATH"
fi
HOST_REPO_PATH="$(cd "$HOST_REPO_PATH" >/dev/null 2>&1 && pwd || true)"

if [ -z "$HOST_REPO_PATH" ] || [ ! -d "$HOST_REPO_PATH" ]; then
    echo "❌ Diretório do repositório não encontrado: $REPO_PATH"
    exit 1
fi

if [ ! -d "$HOST_REPO_PATH/.git" ]; then
    echo "⚠️  .git não encontrado em $HOST_REPO_PATH. Procurando repositório dentro de $HOST_REPO_PATH..."
    CANDIDATE=$(find "$HOST_REPO_PATH" -maxdepth 2 -type d -name .git | head -n1 || true)
    if [ -n "$CANDIDATE" ]; then
        HOST_REPO_PATH="$(dirname "$CANDIDATE")"
        echo "📁 Repositório encontrado em: $HOST_REPO_PATH"
    else
        echo "❌ Nenhum repositório Git encontrado dentro de $HOST_REPO_PATH"
        exit 1
    fi
fi

PROJECT_NAME=${PROJECT_NAME:-$(basename "$HOST_REPO_PATH")}

if [ -z "$PROJECT_NAME" ]; then
    echo "❌ PROJECT_NAME não pôde ser determinado. Defina PROJECT_NAME em .env."
    exit 1
fi

MOUNT_BASE="$(cd "$REPO_PATH" >/dev/null 2>&1 && pwd || true)"
if [ -z "$MOUNT_BASE" ]; then
    echo "❌ Não foi possível determinar o diretório base do volume REPO_PATH."
    exit 1
fi

if [ -d "$MOUNT_BASE/.git" ]; then
    CONTAINER_REPO_PATH="/repo"
else
    REL_PATH="${HOST_REPO_PATH#$MOUNT_BASE/}"
    CONTAINER_REPO_PATH="/repo/$REL_PATH"
fi

if [ ! -d "$HOST_REPO_PATH/.git" ]; then
    echo "❌ O caminho final do repositório não contém .git: $HOST_REPO_PATH"
    exit 1
fi

echo "🧩 Construindo imagem do reprocessor..."
docker compose build reprocessor

echo "🐘 Subindo PostgreSQL..."
docker compose up -d postgres

echo "⏳ Aguardando PostgreSQL ficar pronto..."
until docker compose exec -T postgres pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; do
    printf '.'
    sleep 2
done
printf '\n'
echo "✅ PostgreSQL pronto."

echo "🚀 Executando indexação inicial no repositório: $HOST_REPO_PATH"
docker compose run --rm reprocessor python /app/reprocess.py --repo-path "$CONTAINER_REPO_PATH" --project-name "$PROJECT_NAME"

echo "✅ Setup concluído. Banco, hooks e indexação inicial foram configurados."
