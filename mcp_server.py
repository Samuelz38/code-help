import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

from src.tools.search_db import SearchDB
from src.tools.get_projects import ProjectInfoTool 
from src.tools.index_project import IndexProjectTool
from src.tools.clone_repository import CloneRepositoryTool

# ============================================================
# IMPORT DO COLETOR DE MÉTRICAS (para métricas de nível MCP)
# ============================================================
from metrics_collector import MetricsCollector

# ============================================================
# SERVIDOR MCP COM MÉTRICAS
# ============================================================

mcp = FastMCP("codehelp")

# Inicializa coletor de métricas para o servidor MCP
metrics = MetricsCollector(output_dir="./metrics")


@mcp.tool()
def search_db(query: str, project_name: str = None, limit: int = 5) -> str:
    """
    Busca semântica no banco de dados vetorial.
    Coleta automaticamente: latência (L_query), buffer hit ratio (HR_buf), SSR.
    """
    # Registra chamada da tool
    metrics.record("mcp_call", 1, "count", {
        "tool": "search_db",
        "project_name": project_name,
        "query_preview": query[:50]
    })

    search = SearchDB(query, project_name, limit)
    return search._execute()


@mcp.tool()
def get_project_stats(project_name: str, path:str) -> str:
    """
    Retorna estatísticas do projeto com métricas de performance.
    """
    metrics.record("mcp_call", 1, "count", {
        "tool": "get_project_stats",
        "project_name": project_name,
        "path": path
    })

    stats = ProjectInfoTool(project_name, path)
    return stats.get_project_stats()


@mcp.tool()
def index_project(project_name: str, repo_path: str) -> str:
    """
    Indexa um projeto no banco de dados.
    """
    metrics.record("mcp_call", 1, "count", {
        "tool": "index_project",
        "project_name": project_name
    })

    indexer = IndexProjectTool(repo_path, project_name)
    return indexer._execute()


@mcp.tool()
def clone_repo(repo_url: str, project_name: str) -> str:
    """
    Clona um repositório do GitHub.
    """
    metrics.record("mcp_call", 1, "count", {
        "tool": "clone_repo",
        "project_name": project_name,
        "repo_url": repo_url
    })

    cloner = CloneRepositoryTool(repo_url, project_name)
    return cloner.clone_repository()


@mcp.prompt()
def onboarding_assistant(query: str) -> str:
    """
    Prompt especializado para onboarding de desenvolvedores.
    Coleta métrica de uso do prompt.
    """
    metrics.record("mcp_prompt", 1, "count", {
        "prompt": "onboarding_assistant",
        "query_preview": query[:50]
    })

    return f"""
Você é um assistente técnico especializado em onboarding de desenvolvedores
para projetos de código aberto complexos. Use o contexto do banco de dados
vetorial para responder de forma precisa e educativa.

Pergunta do desenvolvedor: {query}

Diretrizes:
1. Explique conceitos, não apenas forneça código
2. Relacione com a estrutura real do repositório (arquivos, funções)
3. Sugira próximos passos de aprendizado
4. Evite o padrão de "Delegação de IA" — incentive o raciocínio independente
"""


if __name__ == "__main__":
    mcp.run()
