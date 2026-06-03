import os
from pathlib import Path

from git import RemoteProgress, Repo

from src.utils.help_functions import _is_allowed, _resolve_path

class GitProgressHandler(RemoteProgress):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def update(self, op_code, cur_count, max_count=None, message=''):
        if max_count:
            percent = (cur_count / max_count) * 100

            self.callback(percent)


def download_repository_github(link: str, path: str, progress_callback=None):
    find_rigth_bar = link.rfind('/')
    find_rigth_point = link.rfind('.')
    repository_path_name = link[find_rigth_bar + 1 : find_rigth_point]
    full_path = os.path.join(path, repository_path_name)

    if not os.path.exists(full_path):
        Repo.clone_from(
            link,
            full_path,
            depth=1,
            progress=GitProgressHandler(progress_callback or (lambda percent: None)),
        )
    return full_path


class CloneRepositoryTool:
    def __init__(self, link: str, destination: str = "", progress_callback=None):
        self.link = link
        self.destination = destination
        self.progress_callback = progress_callback or (lambda percent: None)

    def clone_repository(self):
        """
        Clona um repositório GitHub para o filesystem local.
        Use para baixar bases de código open-source (ex: OpenCV) para análise.

        Args:
            destination: Subdiretório relativo ao ROOT_DIR (padrão: ROOT_DIR/projects)
        """
        ROOT_DIR = Path(os.getenv("MCP_FS_ROOT", os.path.join(os.getcwd(), "projects"))).resolve()


        try:
            # Valida URL
            if not self.link.startswith(('https://github.com/', 'http://github.com/', 'git@github.com:')):
                return f"❌ URL inválida. Use formato: https://github.com/usuario/repo.git"

            # Resolve caminho de destino
            if self.destination:
                dest_path = _resolve_path(self.destination)
            else:
                dest_path = ROOT_DIR

            if not _is_allowed(dest_path):
                return f"❌ Acesso negado: {dest_path} está fora do diretório permitido."

            # Cria diretório se não existir
            os.makedirs(dest_path, exist_ok=True)

            # Executa o clone (código do seu git_functios.py adaptado)
            full_path = download_repository_github(self.link, str(dest_path), self.progress_callback)

            # Obtém informações do repositório clonado
            repo_name = Path(full_path).name
            file_count = sum(1 for _ in Path(full_path).rglob("*") if _.is_file())
            dir_count = sum(1 for _ in Path(full_path).rglob("*") if _.is_dir())

            result = (
                f"✅ Repositório clonado com sucesso!\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 Nome:        {repo_name}\n"
                f"📁 Caminho:     {full_path}\n"
                f"📄 Arquivos:    {file_count}\n"
                f"📂 Diretórios:  {dir_count}\n"
                f"🔗 URL:         {self.link}\n"
                f"\n"
                f"💡 Dica: Use 'get_project_structure' ou 'list_directory' para explorar o código."
            )

            return result

        except Exception as e:
            return f"❌ Erro ao clonar repositório: {e}"