import os
from pathlib import Path

from src.utils.help_functions import _resolve_path, _is_allowed


class ReadFileTool:
    def __init__(self, file_path, offset, limit):
        self.file_path = file_path
        self.offset = offset
        self.limit = limit

    def read(self):


        ROOT_DIR = Path(os.getenv("MCP_FS_ROOT", os.path.join(os.getcwd(), "projects"))).resolve()


        try:
            path = _resolve_path(self.file_path)

            if not _is_allowed(path):
                return f"❌ Acesso negado: {path} está fora do diretório permitido ({ROOT_DIR})."

            if not path.exists():
                return f"❌ Arquivo não encontrado: {path}"

            if path.is_dir():
                return f"❌ {self.file_path} é um diretório. Use list_directory para navegar."

            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

            total_lines = len(lines)
            start = max(0, self.offset)
            end = min(total_lines, self.offset + self.limit)
            selected = lines[start:end]

            # Formata com números de linha
            numbered = ""
            for i, line in enumerate(selected, start=start):
                numbered += f"{i+1:4d} | {line}"

            header = (
                f"📄 {path.name} ({total_lines} linhas total) — mostrando linhas {start+1}-{end}\n"
                f"Caminho: {path}\n"
                f"{'=' * 60}\n"
            )

            return header + numbered

        except Exception as e:
            return f"❌ Erro ao ler arquivo: {e}"
        
