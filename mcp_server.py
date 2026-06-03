import os
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

from src.tools.search_db import SearchDB
from src.tools.get_projects import ProjectInfoTool

load_dotenv()

# Configuração de Logging
project_root = Path(__file__).parent.resolve()
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "mcp_server.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("mcp-server")


mcp = FastMCP('codehelper-server')


@mcp.tool()
def search_db(query: str, project_name: str = None, limit: int = 5):
    """
    Busca lógica e funcionalidades dentro de bases de código indexadas.
    Use esta ferramenta para encontrar implementações de algoritmos ou localizar funções.
    """
    logger.info(f"Executando search_db: query='{query}', project='{project_name}'")
    search_tool = SearchDB(query, project_name, limit)
    return search_tool._execute()



@mcp.tool()
def get_project_stats(project_name: str):
    
    """
    Retorna estatísticas de um projeto indexado (total de chunks, último commit, etc).
    """
    logger.info(f"Executando get_project_stats: project='{project_name}'")
    project_info = ProjectInfoTool(project_name, '')
    return project_info.get_project_stats()


def main():
    try:
        logger.info("Iniciando MCP server...")
        mcp.run()
    except KeyboardInterrupt:
        logger.info("MCP server interrompido pelo usuário.")
    except Exception as exc:
        logger.error(f"Erro no servidor MCP: {exc}", exc_info=True)


if __name__ == "__main__":
    main()
