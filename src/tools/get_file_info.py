import hashlib
from time import localtime
from src.utils.help_functions import _resolve_path, _is_allowed

class GetFileInfoTool():

    def __init__(self, filepath: str):
        self.filepath = filepath


    def get_file_info(self):
        """
        Retorna metadados de um arquivo (tamanho, extensão, linhas, hash MD5).
        """
        try:
            path = _resolve_path(self.filepath)

            if not _is_allowed(path):
                return f"❌ Acesso negado: {path}"

            if not path.exists():
                return f"❌ Arquivo não encontrado: {path}"

            if path.is_dir():
                return f"❌ {self.filepath} é um diretório."

            stat = path.stat()

            # Conta linhas
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    line_count = sum(1 for _ in f)
            except:
                line_count = "N/A"

            # Hash MD5
            try:
                with open(path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()[:12]
            except:
                file_hash = "N/A"

            mtime = localtime(stat.st_mtime)
            mtime_str = f"{mtime.tm_mday:02d}/{mtime.tm_mon:02d}/{mtime.tm_year} {mtime.tm_hour:02d}:{mtime.tm_min:02d}"

            info = (
                f"📋 Informações do arquivo: {path.name}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Caminho:        {path}\n"
                f"Tamanho:        {stat.st_size:,} bytes\n"
                f"Linhas:         {line_count}\n"
                f"Extensão:       {path.suffix}\n"
                f"Hash (MD5):     {file_hash}\n"
                f"Modificado:     {mtime_str}\n"
                f"Permissões:     {oct(stat.st_mode)[-3:]}\n"
            )
            return info

        except Exception as e:
            return f"❌ Erro: {e}"