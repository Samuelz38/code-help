from pathlib import Path
import os


def _resolve_path(filepath: str) -> Path:
    """Resolve caminho relativo ao ROOT_DIR."""

    ROOT_DIR = Path(os.getenv("MCP_FS_ROOT", os.path.join(os.getcwd(), "projects"))).resolve()

    path = Path(filepath)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def _is_allowed(path: Path) -> bool:
    """Verifica se o caminho está dentro do ROOT_DIR permitido."""

    ROOT_DIR = Path(os.getenv("MCP_FS_ROOT", os.path.join(os.getcwd(), "projects"))).resolve()

    try:
        path.resolve().relative_to(ROOT_DIR)
        return True
    except ValueError:
        return False

def _generate_tree(path: Path, max_depth: int, current_depth: int = 0, prefix: str = "") -> str:
    """Gera árvore de diretórios em formato texto."""
    if current_depth >= max_depth:
        return ""

    result = []
    try:
        items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        # Filtra diretórios ocultos desnecessários
        items = [i for i in items if not (i.name.startswith('.') and i.name not in ['.github', '.vscode'])]

        for i, item in enumerate(items):
            is_last = i == len(items) - 1
            connector = "└── " if is_last else "├── "
            icon = "📁" if item.is_dir() else "📄"

            result.append(f"{prefix}{connector}{icon} {item.name}")

            if item.is_dir():
                extension = "    " if is_last else "│   "
                subtree = _generate_tree(item, max_depth, current_depth + 1, prefix + extension)
                if subtree:
                    result.append(subtree)
    except PermissionError:
        pass

    return "\n".join(result)