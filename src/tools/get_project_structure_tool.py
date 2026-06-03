import os
from pathlib import Path

from src.utils.help_functions import _generate_tree

class GetProjectStructureTool:
    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth


    def get_project_structure(self):
        """
        Retorna a árvore de diretórios do projeto em formato texto.
        Use para entender a organização do código.
        """
        ROOT_DIR = Path(os.getenv("MCP_FS_ROOT", os.path.join(os.getcwd(), "projects"))).resolve()

        try:
            tree = _generate_tree(ROOT_DIR, self.max_depth)
            header = f"🗂️  Estrutura do projeto: {ROOT_DIR.name}\n"
            header += f"Caminho: {ROOT_DIR}\n"
            header += "=" * 60 + "\n"

            return header + tree

        except Exception as e:
            return f"❌ Erro: {e}"