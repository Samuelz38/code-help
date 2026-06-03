import os
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

from src.tools.get_file_info import GetFileInfoTool
from src.tools.get_project_structure_tool import GetProjectStructureTool
from src.tools.list_directory import ListDirectoryTool
from src.tools.read_file import ReadFileTool
from src.tools.search_files import SearchFilesTool
from src.tools.clone_repository import CloneRepositoryTool

load_dotenv()

# Configuração de Logging
project_root = Path(__file__).parent.resolve()
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "mcp_filesystem.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("mcp-filesystem")


mcp = FastMCP('codehelper-filesystem')

# Extensões de código suportadas (alinhado com etl_functions.py)
CODE_EXTENSIONS = {'.cpp', '.hpp', '.h', '.c', '.py', '.js', '.ts', '.md', '.txt', '.json', '.yml', '.yaml'}


@mcp.tool()
def read_file(filepath: str, offset: int = 0, limit: int = 100):
    """
    Lê o conteúdo de um arquivo de código com números de linha.
    Use para inspecionar implementações específicas.
    """
    logger.info(f"Executando read_file: path='{filepath}', offset={offset}, limit={limit}")
    return ReadFileTool(filepath, offset, limit).read()


@mcp.tool()
def list_directory(path: str = "."):
    """
    Lista arquivos e subdiretórios de um caminho.
    Use para navegar pela estrutura do projeto.
    """
    logger.info(f"Executando list_directory: path='{path}'")
    return ListDirectoryTool(path).list_directory()


@mcp.tool()
def search_files(pattern: str, file_pattern: str = "*", max_results: int = 20):
    """
    Busca por padrão de texto em arquivos do projeto (grep-like).
    Use para encontrar onde uma função ou classe é definida.
    """
    logger.info(f"Executando search_files: pattern='{pattern}', file_pattern='{file_pattern}'")
    return SearchFilesTool(pattern, file_pattern, max_results).search()


@mcp.tool()
def get_file_info(filepath: str):
    """
    Retorna metadados de um arquivo (tamanho, extensão, linhas, hash MD5).
    """
    logger.info(f"Executando get_file_info: path='{filepath}'")
    return GetFileInfoTool(filepath).get_file_info()


@mcp.tool()
def get_project_structure(max_depth: int = 3):
    """
    Retorna a árvore de diretórios do projeto em formato texto.
    Use para entender a organização do código.
    """
    logger.info(f"Executando get_project_structure: max_depth={max_depth}")
    return GetProjectStructureTool(max_depth).get_project_structure()

@mcp.tool()
def clone_repository(link: str, destination: str = ""):
    """
    Clona um repositório GitHub para o filesystem local.
    Use para baixar bases de código open-source (ex: OpenCV) para análise.

    Args:
        link: URL do repositório GitHub (ex:
    """
    logger.info(f"Executando clone_repository: link='{link}', destination='{destination}'")
    return CloneRepositoryTool(link, destination).clone_repository()

def main():
    try:
        logger.info("Iniciando MCP filesystem server...")
        mcp.run()
    except KeyboardInterrupt:
        logger.info("MCP filesystem server interrompido pelo usuário.")
    except Exception as exc:
        logger.error(f"Erro no servidor MCP filesystem: {exc}", exc_info=True)


if __name__ == "__main__":
    main()
