import os
import sys
import json
import logging
import hashlib
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

from dotenv import load_dotenv
from psycopg2.extras import execute_values


from src.database.connection import ConectToDataBase
from src.database.etl_process import EmbeddingsETLProcess

# Adiciona raiz do projeto ao path para imports
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))


load_dotenv()

# Configuração de Logging
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "reprocess.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("reprocessor")


class Reprocessor:
    """
    Orquestrador do pipeline de reprocessamento automático.
    Padrão Strategy: diferentes modos de detecção de mudanças.
    """

    def __init__(self, repo_path: str, project_name: str, commit_hash: str = None,
                 commit_msg: str = None):
        self.repo_path = Path(repo_path).resolve()
        self.project_name = project_name
        self.commit_hash = commit_hash or self._get_current_commit()
        self.commit_msg = commit_msg or self._get_commit_message()

        # Configuração do banco via variáveis de ambiente (mesmas do mcp_server.py)
        self.db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "password": os.getenv("DB_PASSWORD", "codehelper123"),
            "dbname": os.getenv("DB_NAME", "codehelper"),
            "user": os.getenv("DB_USER", "codehelper")
        }

        # Validações
        if not self.repo_path.exists():
            raise ValueError(f"Repositório não encontrado: {repo_path}")
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Diretório não é um repositório git: {repo_path}")


    def _get_current_commit(self) -> str:
        """Obtém hash do commit atual via git."""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def _get_commit_message(self) -> str:
        """Obtém mensagem do último commit."""
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%s"],
            cwd=self.repo_path,
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def _get_db_connection(self):
        """Estabelece conexão com PostgreSQL via ConectToDataBase."""
        db = ConectToDataBase(
            self.db_config["host"],
            self.db_config["password"],
            self.db_config["dbname"],
            self.db_config["user"]
        )
        return db.create_connection()

    def _get_changed_files(self) -> List[str]:
        """
        Detecta arquivos modificados comparando hash atual com hash armazenado no banco.
        Estratégia: busca o último commit processado e compara hashes dos arquivos.
        """
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            # Busca hashes do último commit processado para este projeto
            cursor.execute("""
                SELECT DISTINCT file_path, metadata->>'file_hash' as file_hash
                FROM code_vectors
                WHERE metadata->>'project' = %s
                AND commit_hash = (
                    SELECT commit_hash FROM embedding_versions
                    WHERE project_name = %s
                    ORDER BY created_at DESC LIMIT 1
                )
            """, (self.project_name, self.project_name))

            stored_hashes = {row[0]: row[1] for row in cursor.fetchall()}
            cursor.close()
            conn.close()

        except Exception as e:
            stored_hashes = {}

        changed_files = []
        code_extensions = {'.cpp', '.hpp', '.h', '.c', '.py', '.js', '.ts'}

        for filepath in self.repo_path.rglob("*"):
            if filepath.is_file() and filepath.suffix in code_extensions:
                rel_path = str(filepath.relative_to(self.repo_path))
                current_hash = self._file_hash(filepath)

                if rel_path not in stored_hashes or stored_hashes[rel_path] != current_hash:
                    changed_files.append(str(filepath))

        return changed_files

    def _file_hash(self, filepath: Path) -> str:
        """Calcula MD5 de um arquivo."""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _create_etl_log(self) -> int:
        """Cria registro de log do processamento na tabela etl_log."""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO etl_log (project_name, commit_hash, commit_message, status)
                VALUES (%s, %s, %s, 'running')
                RETURNING id
            """, (self.project_name, self.commit_hash, self.commit_msg))

            log_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()

            return log_id

        except Exception as e:
            return "Erro ao criar log ETL: {e}"

    def _update_etl_log(self, log_id: int, **kwargs):
        """Atualiza registro de log com resultados."""
        if log_id is None:
            return

        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            fields = []
            values = []
            for key, value in kwargs.items():
                fields.append(f"{key} = %s")
                values.append(value)

            if fields:
                query = f"UPDATE etl_log SET {', '.join(fields)} WHERE id = %s"
                values.append(log_id)
                cursor.execute(query, values)
                conn.commit()

            cursor.close()
            conn.close()

        except Exception as e:
            return f'Erro ao atualizar log ETL: {e}'

    def _delete_old_chunks(self, file_paths: List[str]) -> int:
        """Remove chunks antigos dos arquivos modificados."""
        if not file_paths:
            return 0

        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            rel_paths = [str(Path(p).relative_to(self.repo_path)) for p in file_paths]

            cursor.execute("""
                DELETE FROM code_vectors
                WHERE metadata->>'project' = %s
                AND file_path = ANY(%s)
            """, (self.project_name, rel_paths))

            deleted = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()

            return deleted

        except Exception as e:
            return f"Erro ao deletar chunks antigos: {e}"

    def _insert_chunks(self, chunks: List[Dict]) -> int:
        """Insere novos chunks com embeddings no banco (batch insert)."""
        if not chunks:
            return 0

        try:
            embeddings = EmbeddingsETLProcess('.')
            vector_model = embeddings.generate_embedding()

            if isinstance(vector_model, str):
                return f'Falha ao carregar modelo: {vector_model}'

            conn = self._get_db_connection()
            cursor = conn.cursor()

            # Prepara dados para inserção em batch

            data = []
            for chunk in chunks:
                embedding = vector_model.embed_query(chunk['content'])
                data.append((
                    chunk['content'],
                    embedding,
                    json.dumps(chunk['metadata']),
                    chunk['file_path'],
                    chunk['chunk_index'],
                    self.commit_hash
                ))

            execute_values(cursor, """
                INSERT INTO code_vectors (content, embedding, metadata, file_path, chunk_index, commit_hash)
                VALUES %s
            """, data, template="(%s, %s::vector, %s, %s, %s, %s)")

            inserted = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()

            return inserted

        except Exception as e:
            return 'Erro ao inserir chunks: {e}'

    def _process_files(self, file_paths: List[str]) -> Tuple[int, int]:
        """
        Processa arquivos modificados: chunking + embeddings + inserção.
        Retorna (chunks_gerados, chunks_inseridos).
        """
        from langchain_core.documents import Document

        all_chunks = []

        for filepath in file_paths:
            path = Path(filepath)
            rel_path = str(path.relative_to(self.repo_path))
            file_hash = self._file_hash(path)

            try:
                # Carrega e faz chunking (reutiliza funções do ETL)
                docs = EmbeddingsETLProcess(str(path.parent)).load_data_path()
                file_docs = [d for d in docs if d.metadata.get('source', '') == str(path)]

                if not file_docs:
                    continue

                chunks = EmbeddingsETLProcess(str(path.parent)).chunk_documents(file_docs)

                for i, chunk in enumerate(chunks):
                    chunk.metadata.update({
                        'project': self.project_name,
                        'file_path': rel_path,
                        'file_hash': file_hash,
                        'commit_hash': self.commit_hash,
                        'chunk_index': i,
                        'total_chunks': len(chunks),
                        'processed_at': datetime.now().isoformat()
                    })
                    all_chunks.append({
                        'content': chunk.page_content,
                        'metadata': chunk.metadata,
                        'file_path': rel_path,
                        'chunk_index': i
                    })

            except Exception as e:
                return f'Erro ao processar {rel_path}: {e}'

        # Insere no banco
        inserted = self._insert_chunks(all_chunks)

        return len(all_chunks), inserted

    def _register_version(self, total_chunks: int):
        """Registra versão de embeddings para este commit."""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO embedding_versions (project_name, commit_hash, commit_date, total_chunks)
                VALUES (%s, %s, NOW(), %s)
                ON CONFLICT (project_name, commit_hash) DO UPDATE
                SET total_chunks = EXCLUDED.total_chunks, created_at = NOW()
            """, (self.project_name, self.commit_hash, total_chunks))

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            return f'Erro ao registrar versão: {e}'

    def run(self):
        """Executa o pipeline completo de reprocessamento."""
        logger.info(f"{'='*60}")
        logger.info(f"🚀 PIPELINE DE REPROCESSAMENTO AUTOMÁTICO")
        logger.info(f"{'='*60}")
        logger.info(f"📁 Repositório: {self.repo_path}")
        logger.info(f"🏷️  Projeto:    {self.project_name}")
        logger.info(f"🔖 Commit:      {self.commit_hash[:8]}")
        logger.info(f"💬 Mensagem:    {self.commit_msg}")
        logger.info(f"⏰ Início:      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")

        # 1. Cria log
        log_id = self._create_etl_log()

        try:
            # 2. Detecta arquivos modificados
            changed_files = self._get_changed_files()

            if not changed_files:
                logger.info("✅ Nenhuma mudança detectada. Banco já está sincronizado.")
                self._update_etl_log(
                    log_id,
                    status="completed",
                    finished_at=datetime.now(),
                    files_processed=0,
                    chunks_inserted=0
                )
                return

            logger.info(f"📄 {len(changed_files)} arquivo(s) modificado(s):")
            for f in changed_files[:5]:
                logger.info(f"   • {Path(f).name}")
            if len(changed_files) > 5:
                logger.info(f"   ... e mais {len(changed_files) - 5} arquivo(s)")

            # 3. Remove chunks antigos
            logger.info("🗑️  Removendo embeddings antigos...")
            deleted = self._delete_old_chunks(changed_files)

            # 4. Reprocessa arquivos modificados
            logger.info("⚙️  Reprocessando arquivos (chunking + embeddings)...")
            chunks_generated, chunks_inserted = self._process_files(changed_files)

            # 5. Registra versão
            self._register_version(chunks_inserted)

            # 6. Finaliza log
            self._update_etl_log(
                log_id,
                status="completed",
                finished_at=datetime.now(),
                files_processed=len(changed_files),
                chunks_inserted=chunks_inserted,
                chunks_deleted=deleted
            )

            logger.info(f"{'='*60}")
            logger.info(f"✅ REPROCESSAMENTO CONCLUÍDO COM SUCESSO")
            logger.info(f"{'='*60}")
            logger.info(f"⏰ Término: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"📊 Resumo:")
            logger.info(f"   • Arquivos processados: {len(changed_files)}")
            logger.info(f"   • Chunks gerados:       {chunks_generated}")
            logger.info(f"   • Chunks inseridos:     {chunks_inserted}")
            logger.info(f"   • Chunks removidos:     {deleted}")
            logger.info(f"{'='*60}")

        except Exception as e:
            logger.error(f"❌ ERRO NO REPROCESSAMENTO: {e}", exc_info=True)

            self._update_etl_log(
                log_id,
                status="failed",
                finished_at=datetime.now(),
                error_message=str(e)
            )

            raise


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline de reprocessamento automático de embeddings"
    )
    parser.add_argument("--repo-path", required=True, help="Caminho do repositório git")
    parser.add_argument("--project-name", required=True, help="Nome do projeto (ex: opencv)")
    parser.add_argument("--commit-hash", default=None, help="Hash do commit (opcional)")
    parser.add_argument("--commit-msg", default=None, help="Mensagem do commit (opcional)")

    args = parser.parse_args()

    reprocessor = Reprocessor(
        repo_path=args.repo_path,
        project_name=args.project_name,
        commit_hash=args.commit_hash,
        commit_msg=args.commit_msg
    )

    reprocessor.run()


if __name__ == "__main__":
    main()
