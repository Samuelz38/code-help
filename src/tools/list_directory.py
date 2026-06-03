import os
from pathlib import Path

from src.utils.help_functions import _resolve_path, _is_allowed

class ListDirectoryTool:
    def __init__(self, root_dir):
        self.root_dir = root_dir

    def list_directory(self):
        # Implementação para listar o conteúdo do diretório

        ROOT_DIR = Path(os.getenv("MCP_FS_ROOT", os.path.join(os.getcwd(), "projects"))).resolve()


        try:
            dir_path = _resolve_path(self.root_dir)

            if not _is_allowed(dir_path):
                return f"❌ Acesso negado: {dir_path}"

            if not dir_path.exists():
                return f"❌ Diretório não encontrado: {dir_path}"

            if not dir_path.is_dir():
                return f"❌ {self.root_dir} não é um diretório."

            items = []

            try:
                for item in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                    prefix = "📁" if item.is_dir() else "📄"
                    suffix = "/" if item.is_dir() else ""
                    size_info = ""
                    if item.is_file():
                        size = item.stat().st_size
                        size_info = f" ({size:,} bytes)"
                    items.append(f"{prefix} {item.name}{suffix}{size_info}")
            
            except PermissionError:
                return f"❌ Permissão negada: {dir_path}"

            rel = str(dir_path.relative_to(ROOT_DIR)) if dir_path != ROOT_DIR else '.'
            header = f"📂 Diretório: {rel}\n"
            header += f"Caminho completo: {dir_path}\n"
            header += "-" * 40 + "\n"

            return header + "\n".join(items) if items else header + "(diretório vazio)"

        except Exception as e:
            return f"❌ Erro: {e}"