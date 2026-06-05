# CodeHelper - Assistente de Análise de Código com MCP e Busca Semântica

> Sistema de mentoria automatizada para desenvolvedores iniciantes explorarem bases de código complexas (ex: OpenCV) via linguagem natural, usando Model Context Protocol (MCP), PostgreSQL + pgvector, e CI/CD local com Docker.

---

## 📋 Índice

- [O que é o CodeHelper?](#-o-que-é-o-codehelper)
- [Arquitetura do Sistema](#-arquitetura-do-sistema)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação Rápida (5 minutos)](#-instalação-rápida-5-minutos)
- [Uso com Claude Desktop / Cursor](#-uso-com-claude-desktop--cursor)
- [Como Usar (Passo a Passo)](#-como-usar-passo-a-passo)
- [Fluxo de CI/CD Automático](#-fluxo-de-cicd-automático)
- [Serviços e Portas](#-serviços-e-portas)
- [Troubleshooting](#-troubleshooting)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Tecnologias Utilizadas](#-tecnologias-utilizadas)

---

## 🤖 O que é o CodeHelper?

O **CodeHelper** é um sistema que permite você fazer perguntas em **linguagem natural** sobre bases de código complexas (como o OpenCV) e receber respostas com:

- **Código relevante** encontrado semanticamente (não apenas por texto exato)
- **Explicações** do que o código faz
- **Navegação** pelos arquivos do projeto

### Exemplo de uso:

> **Você pergunta:** *"Como funciona o GaussianBlur no OpenCV?"*
>
> **CodeHelper responde:** *"O GaussianBlur é implementado em `modules/imgproc/src/smooth.cpp`. Ele aplica um kernel gaussiano 2D separável para suavizar a imagem. Aqui está o código: [...]"*

---

## 🏗️ Arquitetura do Sistema

```
┌─────────────────┐     stdio      ┌─────────────────────┐
│  Claude Desktop │◄──────────────►│  MCP Server Vector  │
│  Cursor / IDE   │                  │  (search_db)        │
└─────────────────┘                  └──────────┬──────────┘
       │                                       │
       │          stdio                        │ SQL
       │◄────────────────────────────────────►│
       │         MCP Server FS                 │
       │         (read_file, clone, etc)       │
       │                                       │
       │         Docker Compose                │
       │    ┌────────────────────────┐         │
       └───►│  PostgreSQL + pgvector │◄────────┘
            │  ├── code_vectors      │
            │  ├── etl_log           │
            │  └── embedding_versions│
            └────────────────────────┘
                      ▲
                      │ docker compose run --rm reprocessor
                      │
            ┌─────────┴──────────┐
            │  Git Hooks         │
            │  ├── pre-commit    │  (detecta mudanças)
            │  └── post-commit   │  (aciona reprocessamento)
            └────────────────────┘
                      ▲
                      │ git commit
            ┌─────────┴──────────┐
            │  Repositório       │
            │  OpenCV (local)    │
            └────────────────────┘
```

---

## 📦 Pré-requisitos

Antes de começar, você precisa ter instalado:

| Software | Versão | Como verificar |
|----------|--------|----------------|
| **Docker** | 20.10+ | `docker --version` |
| **Docker Compose** | 2.0+ | `docker compose version` |
| **Git** | 2.30+ | `git --version` |
| **Python** | 3.11+ | `python --version` *(apenas para MCP local)* |

> **Nota:** O projeto roda **100% em Docker**. Você só precisa do Python se for usar os MCP servers localmente (fora do Docker).

---

## 🚀 Instalação Rápida (5 minutos)

### Passo 1: Clone o repositório

```bash
git clone https://github.com/Samuelz38/code-help.git
cd code-help
```

### Passo 2: Configure as variáveis de ambiente

```bash
# Copie o template de variáveis
cp .env.example .env

# Edite o arquivo .env com suas configurações
# (principalmente o HF_TOKEN para embeddings)
nano .env
```

**Variáveis importantes no `.env`:**

```bash
# PostgreSQL (não precisa alterar se for usar localmente)
DB_HOST=postgres
DB_NAME=codehelper
DB_USER=codehelper
DB_PASSWORD=codehelper123
DB_PORT=5432

# HuggingFace (obrigatório para gerar embeddings)
# Obtenha em: https://huggingface.co/settings/tokens
HF_TOKEN=hf_seu_token_aqui

# Repositório a analisar (padrão: OpenCV)
REPO_PATH=./projects/opencv
PROJECT_NAME=opencv

# pgAdmin (opcional)
PGADMIN_EMAIL=admin@codehelper.local
PGADMIN_PASSWORD=admin123
PGADMIN_PORT=5050
```

> **Como obter o HF_TOKEN:** Acesse [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens), clique em "New token", dê o nome "codehelper", selecione tipo **Read**, e copie o token.

### Passo 3: Execute o setup automático

```bash
./setup.sh
```

**O que o `setup.sh` faz automaticamente:**

1. ✅ Verifica se Docker está instalado
2. ✅ Cria o arquivo `.env` (se não existir)
3. ✅ Build da imagem Docker do reprocessor
4. ✅ Sobe o PostgreSQL + pgvector
5. ✅ Aguarda o banco ficar pronto (healthcheck)
6. ✅ Clona o repositório OpenCV (se não existir)
7. ✅ Instala os Git Hooks no repositório
8. ✅ **Indexa o projeto pela primeira vez** (gera embeddings)
9. ✅ Inicia todos os serviços (monitoring, MCP servers)

> ⏳ **Atenção:** A indexação inicial pode levar **10-30 minutos** dependendo do tamanho do repositório. Não cancele o processo!

### Passo 4: Verifique se está funcionando

```bash
# Veja os containers rodando
docker compose ps

# Saída esperada:
# NAME                    STATUS
# codehelper-postgres     running (healthy)
# codehelper-reprocessor  exited (0)  ← normal, roda sob demanda
# codehelper-prometheus   running
# codehelper-loki         running
# codehelper-promtail     running
# codehelper-grafana      running
```

---

## 💻 Uso com Claude Desktop / Cursor

Para usar o CodeHelper com **Claude Desktop** ou **Cursor IDE**, você precisa rodar os MCP servers **localmente** (fora do Docker), pois esses clientes se conectam via `stdio` local.

### Passo 1: Instale as dependências Python

```bash
# Crie um ambiente virtual (recomendado)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Instale as dependências
pip install -r requirements.txt
```

### Passo 2: Configure as variáveis de ambiente no host

```bash
# Copie o .env para o ambiente local
cp .env .env.local

# Ou exporte manualmente:
export DB_HOST=localhost
export DB_NAME=codehelper
export DB_USER=codehelper
export DB_PASSWORD=codehelper123
export HF_TOKEN=hf_seu_token_aqui
export MCP_FS_ROOT=./projects
```

### Passo 3: Inicie os MCP servers

```bash
# Terminal 1: Servidor de busca vetorial
python mcp_server.py

# Terminal 2: Servidor de filesystem
python mcp_server_filesystem.py
```

### Passo 4: Configure o cliente MCP

**Claude Desktop:**

Edite `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "codehelper-vector": {
      "type": "stdio",
      "command": "/caminho/para/venv/bin/python",
      "args": ["/caminho/para/code-help/mcp_server.py"],
      "env": {
        "DB_HOST": "localhost",
        "DB_NAME": "codehelper",
        "DB_USER": "codehelper",
        "DB_PASSWORD": "codehelper123",
        "HF_TOKEN": "hf_seu_token_aqui"
      }
    },
    "codehelper-filesystem": {
      "type": "stdio",
      "command": "/caminho/para/venv/bin/python",
      "args": ["/caminho/para/code-help/mcp_server_filesystem.py"],
      "env": {
        "MCP_FS_ROOT": "/caminho/para/code-help/projects"
      }
    }
  }
}
```

**Cursor IDE:**

Vá em `Settings > MCP` e adicione os servidores com a configuração acima.

---

## 🎯 Como Usar (Passo a Passo)

### Cenário 1: Primeira vez analisando um projeto

```
Você: "Analise o OpenCV para mim"

Assistente: "Vou baixar e indexar o OpenCV. Isso pode levar alguns minutos..."

[Assistente executa automaticamente:]
→ clone_repository("https://github.com/opencv/opencv.git")
→ index_project("./projects/opencv", "opencv")

Assistente: "✅ OpenCV indexado! Agora vou buscar informações..."

[Assistente executa:]
→ search_db("Gaussian blur implementation", "opencv")

Assistente: "Encontrei a implementação em smooth.cpp. Vou mostrar o código..."

[Assistente executa:]
→ read_file("modules/imgproc/src/smooth.cpp", offset=180, limit=40)

Assistente: "O OpenCV implementa GaussianBlur aplicando um kernel gaussiano
           2D separável para suavizar a imagem. A função principal está
           nas linhas 180-220 de smooth.cpp..."
```

### Cenário 2: Projeto já indexado

```
Você: "Busque funções de detecção de borda"

Assistente: "Verificando se o projeto está indexado..."

[Assistente executa:]
→ get_project_stats("opencv")

Assistente: "✅ Projeto encontrado com 15.234 chunks. Buscando..."

[Assistente executa:]
→ search_db("edge detection algorithm", "opencv")

Assistente: "Encontrei 3 implementações relevantes:
           1. edge_detector.cpp (similarity: 0.91)
           2. sobel_filter.cpp (similarity: 0.84)
           3. canny.cpp (similarity: 0.79)

           Quer que eu mostre algum desses arquivos?"
```

### Cenário 3: Explorar código específico

```
Você: "Mostre o arquivo que implementa o resize"

[Assistente executa:]
→ search_db("image resize interpolation", "opencv")

[Resultado aponta resize.cpp]

Assistente: "Encontrei em modules/imgproc/src/resize.cpp.
           Vou mostrar as primeiras 100 linhas."

[Assistente executa:]
→ read_file("modules/imgproc/src/resize.cpp", offset=0, limit=100)
```

---

## 🔄 Fluxo de CI/CD Automático

Após a configuração inicial, o sistema mantém os embeddings **automaticamente atualizados** quando você edita o código:

```
Você edita: modules/core/src/matrix.cpp
    │
    ▼
git add .
    │
    ▼
git commit -m "refactor: otimização de loop"
    │
    ├──────────────────────────────────────┐
    ▼                                      ▼
┌─────────────┐                    ┌─────────────┐
│ pre-commit  │                    │ post-commit │
│ (host)      │                    │ (host)      │
│             │                    │             │
│ 1. Detecta  │                    │ 1. Verifica │
│    .cpp     │                    │    marker   │
│ 2. Cria     │                    │ 2. docker   │
│    marker   │                    │    compose  │
│    file     │                    │    exec     │
└─────────────┘                    └─────────────┘
                                          │
                                          ▼
                                   ┌─────────────┐
                                   │  Container  │
                                   │  Reprocessor│
                                   │             │
                                   │ 1. Detecta │
                                   │    mudanças │
                                   │    (hash)   │
                                   │ 2. Remove   │
                                   │    chunks   │
                                   │    antigos  │
                                   │ 3. Gera     │
                                   │    novos    │
                                   │    embeds   │
                                   │ 4. INSERT   │
                                   │    no banco │
                                   └─────────────┘
                                          │
                                          ▼
                                   ┌─────────────┐
                                   │  PostgreSQL │
                                   │  + pgvector │
                                   │             │
                                   │  code_vectors│
                                   │  ATUALIZADO │
                                   │  ✅          │
                                   └─────────────┘
```

**Como funciona:**

1. Você edita um arquivo `.cpp` ou `.py` no repositório
2. Faz `git add .` e `git commit`
3. O hook `pre-commit` detecta que arquivos de código mudaram
4. O hook `post-commit` aciona o reprocessamento **dentro do Docker**
5. O container `reprocessor` detecta mudanças por hash, remove chunks antigos e gera novos embeddings
6. O banco PostgreSQL é atualizado automaticamente!

> **Você não precisa fazer nada manualmente.** O sistema mantém os embeddings sincronizados com o código.

---

## 🌐 Serviços e Portas

Após executar `./setup.sh`, os seguintes serviços estarão disponíveis:

| Serviço | URL | Descrição |
|---------|-----|-----------|
| **PostgreSQL** | `localhost:5432` | Banco de dados com pgvector |
| **pgAdmin** | `http://localhost:5050` | Interface web para gerenciar o banco |
| **Grafana** | `http://localhost:3000` | Dashboards de monitoramento |
| **Prometheus** | `http://localhost:9090` | Métricas do sistema |
| **Loki** | `http://localhost:3100` | Agregação de logs |

**Credenciais padrão:**
- **pgAdmin:** `admin@codehelper.local` / `admin123`
- **Grafana:** `admin` / `admin` (altere no primeiro login)

---

## 🔧 Troubleshooting

### "Nenhum resultado encontrado" no search_db

**Causa:** O projeto não foi indexado.

**Solução:**
```bash
# Verifique se o projeto está no banco
docker compose exec postgres psql -U codehelper -d codehelper -c "SELECT COUNT(*) FROM code_vectors WHERE metadata->>'project' = 'opencv';"

# Se retornar 0, indexe manualmente:
docker compose run --rm reprocessor python /app/reprocess.py --repo-path /repo --project-name opencv
```

### "Erro ao conectar ao banco"

**Causa:** PostgreSQL não está rodando.

**Solução:**
```bash
# Verifique se o container está rodando
docker compose ps

# Se não estiver, suba o banco
docker compose up -d postgres

# Aguarde o healthcheck
docker compose logs -f postgres
```

### "Erro ao gerar embedding"

**Causa:** `HF_TOKEN` não configurado ou inválido.

**Solução:**
```bash
# Verifique se o token está no .env
grep HF_TOKEN .env

# Teste o token
curl -H "Authorization: Bearer hf_seu_token" https://huggingface.co/api/whoami
```

### "Docker não encontrado no host" (hooks)

**Causa:** Docker não está no PATH do hook.

**Solução:** Certifique-se de que o Docker está instalado e acessível no terminal onde você faz `git commit`.

### Performance lenta no search_db

**Causa:** Modelo de embeddings sendo carregado a cada query.

**Solução:** Já está resolvido! O projeto usa cache Singleton (`EmbeddingsETLProcess._embedding_model`). A primeira query pode demorar 2-5s, as seguintes são instantâneas.

---

## 📁 Estrutura do Projeto

```
code-help/
├── src/
│   ├── prompts.py                  ← Prompts MCP (@mcp.prompt)
│   ├── database/
│   │   ├── connection.py           ← Conexão PostgreSQL + pgvector
│   │   └── etl_process.py          ← Pipeline ETL (load, chunk, embed, cache)
│   └── tools/
│       ├── index_project.py        ← Indexação de projetos (ETL + INSERT)
│       ├── search_db.py            ← Busca semântica (SELECT <=> vector)
│       ├── clone_repository.py     ← Clone de repos GitHub
│       ├── read_file.py            ← Leitura de arquivos
│       ├── list_directory.py       ← Listagem de diretórios
│       ├── search_files.py         ← Busca grep-like
│       ├── get_file_info.py        ← Metadados de arquivo
│       └── get_project_structure.py ← Árvore de diretórios
│
├── mcp_server.py                   ← Servidor MCP Vetorial
├── mcp_server_filesystem.py        ← Servidor MCP Filesystem
├── reprocess.py                    ← Script CLI de reprocessamento (CI/CD)
├── setup.sh                        ← Setup automático (execute 1x)
├── docker-entrypoint.sh          ← Entrypoint do container (instala hooks)
├── docker-compose.yml            ← Orquestração Docker
├── Dockerfile.reprocessor          ← Imagem Docker do reprocessor
├── .env.example                    ← Template de variáveis
├── requirements.txt                ← Dependências Python
├── requirements.docker.txt         ← Dependências Docker
├── git-hooks/
│   ├── pre-commit.sh             ← Detecta mudanças em código
│   ├── post-commit.sh            ← Aciona reprocessamento no Docker
│   └── install_hooks.sh          ← Instala hooks manualmente
└── monitoring/
    ├── prometheus.yml              ← Configuração Prometheus
    ├── loki-config.yml             ← Configuração Loki
    ├── promtail-config.yml         ← Configuração Promtail
    └── grafana/
        └── datasources/
            └── datasource.yml      ← Data sources Grafana
```

---

## 🛠️ Tecnologias Utilizadas

| Tecnologia | Uso |
|------------|-----|
| **Python 3.11+** | Linguagem principal |
| **FastMCP** | Servidores MCP (Model Context Protocol) |
| **PostgreSQL 16** | Banco de dados relacional |
| **pgvector** | Extensão vetorial para PostgreSQL |
| **LangChain** | Chunking e processamento de documentos |
| **HuggingFace** | Modelo de embeddings (all-MiniLM-L6-v2) |
| **Docker + Compose** | Containerização e orquestração |
| **Git + Hooks** | CI/CD local automatizado |
| **Prometheus** | Métricas e monitoramento |
| **Loki + Promtail** | Agregação de logs |
| **Grafana** | Dashboards de observabilidade |

---

## 📝 Notas para Desenvolvedores

### Como adicionar um novo projeto para análise

```bash
# 1. Clone o repositório
git clone https://github.com/usuario/projeto.git ./projects/meu-projeto

# 2. Indexe o projeto
./setup.sh
# ou manualmente:
docker compose run --rm reprocessor python /app/reprocess.py --repo-path /repo --project-name meu-projeto

# 3. Use no Claude/Cursor com project_name="meu-projeto"
```

### Como reindexar após mudanças manuais

```bash
# Se você editar arquivos fora do Git (sem commit):
docker compose run --rm reprocessor python /app/reprocess.py --repo-path /repo --project-name opencv
```

### Como verificar estatísticas do banco

```bash
# Total de chunks por projeto
docker compose exec postgres psql -U codehelper -d codehelper -c "SELECT metadata->>'project' as projeto, COUNT(*) as chunks FROM code_vectors GROUP BY projeto;"

# Último reprocessamento
docker compose exec postgres psql -U codehelper -d codehelper -c "SELECT * FROM etl_log ORDER BY finished_at DESC LIMIT 3;"
```

---

## 📄 Licença

Este projeto foi desenvolvido como Trabalho de Conclusão de Curso (TCC) em Engenharia de Software.

**Autor:** Samuel Victor Avelino Araújo
**Orientador:** Prof. Me. Felipe
**Instituição:** Centro Universitário Unidade de Ensino Superior Dom Bosco (UNDB)
**Ano:** 2026

---

## 🤝 Contribuição

Para reportar bugs ou sugerir melhorias, abra uma issue no GitHub:
https://github.com/Samuelz38/code-help/issues
