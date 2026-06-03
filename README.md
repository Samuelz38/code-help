# Code Help

Este projeto reúne um conjunto de ferramentas para análise de código, reprocessamento de embeddings, e execução de servidores MCP (Model Context Protocol) usando Docker Compose.

## O que o projeto faz

- Inicia um banco de dados PostgreSQL com suporte a `pgvector` para armazenar embeddings de código.
- Executa um pipeline de reprocessamento de arquivos de código para gerar e atualizar embeddings no banco.
- Disponibiliza dois servidores MCP:
  - `codehelper-server`: ferramenta de busca semântica em código via `search_db` e `get_project_stats`.
  - `codehelper-filesystem`: ferramentas de exploração de projetos e arquivos via `list_directory`, `read_file`, `search_files`, `get_file_info`, `get_project_structure` e `clone_repository`.
- Orquestra serviços de monitoramento com Prometheus, Loki, Promtail e Grafana.

## Principais arquivos

- `docker-compose.yml`: define os serviços do projeto, incluindo `postgres`, `reprocessor`, `prometheus`, `loki`, `promtail`, `grafana`, `mcp-server` e `mcp-filesystem`.
- `Dockerfile`: constrói a imagem base usada pelos serviços Python (`reprocessor`, `mcp-server`, `mcp-filesystem`).
- `reprocess.py`: pipeline principal para detectar alterações em repositórios Git, gerar embeddings e inserir no banco.
- `mcp_server.py`: servidor MCP que expõe ferramentas de busca e estatísticas de projetos.
- `mcp_server_filesystem.py`: servidor MCP que expõe ferramentas de inspeção de arquivos e navegação de diretório.
- `requirements.docker.txt`: dependências Python instaladas na imagem Docker.
- `monitoring/`: contém configurações de Prometheus, Loki, Promtail e Grafana.
- `git-hooks/`: scripts de hook Git para acionar reprocessamento automático em commits ou pushes.

## Como usar

1. Configure o arquivo `.env` com as variáveis de ambiente necessárias.
2. Execute `docker compose up -d --build` para subir todos os serviços.
3. Acesse Grafana em `http://localhost:3000`, Prometheus em `http://localhost:9090` e Loki em `http://localhost:3100`.

## Observações

- Os MCP servers são iniciados automaticamente via Docker Compose.
- O serviço `reprocessor` atua sobre um diretório de repositório Git montado no container e processa apenas aquele caminho.
- A configuração do Grafana já inclui datasources para Prometheus e Loki.
