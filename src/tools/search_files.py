import re
import os
from pathlib import Path

from src.utils.help_functions import _is_allowed


class SearchFilesTool():
   
    def __init__(self,pattern: str, file_pattern: str = "*", max_results: int = 20):
        self.pattern = pattern
        self.file_pattern = file_pattern
        self.max_results = max_results



    def search(self):
        """
        Busca por padrão de texto em arquivos do projeto (grep-like).
        Use para encontrar onde uma função ou classe é definida.
        """

        ROOT_DIR = Path(os.getenv("MCP_FS_ROOT", os.path.join(os.getcwd(), "projects"))).resolve()


        if not self.pattern:
            return "❌ Padrão de busca vazio."

        try:
            regex = re.compile(self.pattern, re.IGNORECASE)
        except re.error as e:
            return f"❌ Expressão regular inválida: {e}"

        results = []
        count = 0

        try:
            for item in ROOT_DIR.rglob(self.file_pattern):
                if item.is_file() and _is_allowed(item):
                    # Pula arquivos binários grandes
                    if item.stat().st_size > 5 * 1024 * 1024:  # 5MB
                        continue

                    try:
                        with open(item, 'r', encoding='utf-8', errors='replace') as f:
                            for line_num, line in enumerate(f, 1):
                                if regex.search(line):
                                    rel = item.relative_to(ROOT_DIR)
                                    results.append(f"  {rel}:{line_num}  {line.strip()[:120]}")
                                    count += 1
                                    if count >= self.max_results:
                                        break
                            if count >= self.max_results:
                                break
                    except (UnicodeDecodeError, PermissionError):
                        continue
        except Exception as e:
            return f"❌ Erro durante a busca: {e}"
        header = f"🔍 Busca por '{self.pattern}' ({count} resultado(s))\n"
        header += f"Diretório: {ROOT_DIR}\n"
        header += "=" * 60 + "\n"

        if not results:
            return header + "Nenhum resultado encontrado."

        return header + "\n".join(results)