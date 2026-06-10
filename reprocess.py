import os
import sys
import json
import logging
import hashlib
import argparse
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

from dotenv import load_dotenv
from psycopg2.extras import execute_values

from src.database.connection import ConectToDataBase
from src.database.etl_process import EmbeddingsETLProcess

# ============================================================
# IMPORT DO COLETOR DE MÉTRICAS
# ============================================================
from metrics_collector import MetricsCollector, count_repository_lines

project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

load_dotenv()

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
    VERSÃO BATCH: processa embeddings em lotes para máxima performance.
    """

    def __init__(self, repo_path: str, project_name: str, commit_hash: str = None,
                 commit_msg: str = None):
        self.repo_path = Path(repo_path).resolve()
        self.project_name = project_name
        self.commit_hash = commit_hash or self._get_current_commit()
        self.commit_msg = commit_msg or self._get_commit_message()

        self.db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "password": os.getenv("DB_PASSWORD", "codehelper123"),
            "dbname": os.getenv("DB_NAME", "codehelper"),
            "user": os.getenv("DB_USER", "codehelper")
        }

        # ============================================================
        # INICIALIZA COLETOR DE MÉTRICAS
        # ============================================================
        self.metrics = MetricsCollector(
            db_config=self.db_config,
            output_dir=str(project_root / "metrics")
        )

        # Cache do total de linhas do repositório (para SSR)
        self._total_lines = None

        # ============================================================
        # INSTÂNCIA ÚNICA DO ETL (singleton de embeddings)
        # ============================================================
        self.etl_process = EmbeddingsETLProcess(str(self.repo_path))
        # Pré-carrega o modelo de embeddings uma única vez
        logger.info("⚡ Pré-carregando modelo de embeddings...")
        self.embedding_model = self.etl_process.generate_embedding()
        logger.info("✅ Modelo de embeddings carregado com sucesso!")

        if not self.repo_path.exists():
            raise ValueError(f"Repositório não encontrado: {repo_path}")
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Diretório não é um repositório git: {repo_path}")

    def _get_current_commit(self) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def _get_commit_message(self) -> str:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%s"],
            cwd=self.repo_path,
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def _get_db_connection(self):
        db = ConectToDataBase(
            self.db_config["host"],
            self.db_config["password"],
            self.db_config["dbname"],
            self.db_config["user"]
        )
        return db.create_connection()

    def _get_total_lines(self) -> int:
        """Cache do total de linhas do repositório (para SSR)."""
        if self._total_lines is None:
            self._total_lines = count_repository_lines(str(self.repo_path))
            logger.info(f"📏 Total de linhas no repositório: {self._total_lines:,}")
        return self._total_lines

    def _get_changed_files(self) -> List[str]:
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
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
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _create_etl_log(self) -> int:
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
            logger.error(f"Erro ao criar log ETL: {e}")
            raise

    def _update_etl_log(self, log_id: int, **kwargs):
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
            logger.error(f"Erro ao atualizar log ETL: {e}")
            raise

    def _delete_old_chunks(self, file_paths: List[str]) -> int:
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
            logger.error(f"Erro ao deletar chunks antigos: {e}")
            raise

    def _insert_chunks_batch(self, chunks: List[Dict]) -> int:
        """
        VERSÃO BATCH: processa todos os embeddings de uma vez em lotes.
        Reduz de milhares de chamadas para dezenas de batches.
        """
        if not chunks:
            return 0

        BATCH_SIZE = 64  # Processa 64 chunks por vez — ótimo para CPU
        total_inserted = 0

        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            # Processa em batches
            for batch_start in range(0, len(chunks), BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, len(chunks))
                batch = chunks[batch_start:batch_end]

                # Gera embeddings em batch (MUITO mais rápido!)
                contents = [c['content'] for c in batch]
                embeddings = self.embedding_model.embed_documents(contents)

                # Prepara dados para inserção
                data = []
                for chunk, embedding in zip(batch, embeddings):
                    data.append((
                        chunk['content'],
                        embedding,
                        json.dumps(chunk['metadata']),
                        chunk['file_path'],
                        chunk['chunk_index'],
                        self.commit_hash
                    ))

                # Insere no banco
                execute_values(cursor, """
                    INSERT INTO code_vectors (content, embedding, metadata, file_path, chunk_index, commit_hash)
                    VALUES %s
                """, data, template="(%s, %s::vector, %s, %s, %s, %s)")

                batch_inserted = cursor.rowcount
                total_inserted += batch_inserted

                # Log de progresso a cada batch
                if (batch_start // BATCH_SIZE) % 10 == 0:
                    progress = (batch_end / len(chunks)) * 100
                    logger.info(f"📊 Progresso: {progress:.1f}% ({batch_end}/{len(chunks)} chunks)")

            conn.commit()
            cursor.close()
            conn.close()
            return total_inserted

        except Exception as e:
            logger.error(f"Erro ao inserir chunks em batch: {e}")
            raise

    def _load_single_file(self, filepath: Path) -> List:
        """Carrega APENAS o arquivo individual."""
        from langchain_core.documents import Document
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            doc = Document(
                page_content=content,
                metadata={'source': str(filepath)}
            )
            return [doc]
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível ler {filepath}: {e}")
            return []

    def _process_files(self, file_paths: List[str]) -> Tuple[int, int]:
        """
        Processa arquivos em chunks e insere no banco.
        VERSÃO BATCH: acumula TODOS os chunks antes de gerar embeddings.
        """
        all_chunks = []

        # FASE 1: Chunking (rápido, sem embeddings)
        logger.info("📝 Fase 1: Chunking dos arquivos...")
        for idx, filepath in enumerate(file_paths, 1):
            path = Path(filepath)
            rel_path = str(path.relative_to(self.repo_path))
            file_hash = self._file_hash(path)

            if idx % 500 == 0:
                logger.info(f"   Chunking: {idx}/{len(file_paths)} arquivos ({idx/len(file_paths)*100:.1f}%)")

            try:
                file_docs = self._load_single_file(path)
                if not file_docs:
                    continue

                chunks = self.etl_process.chunk_documents(file_docs)

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
                logger.error(f"❌ Erro ao processar {rel_path}: {e}")
                raise

        logger.info(f"✅ Fase 1 concluída: {len(all_chunks)} chunks gerados de {len(file_paths)} arquivos")

        # FASE 2: Embeddings em batch (a parte lenta, mas otimizada)
        logger.info("🧠 Fase 2: Gerando embeddings em batch...")
        inserted = self._insert_chunks_batch(all_chunks)

        return len(all_chunks), inserted

    def _register_version(self, total_chunks: int):
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
            logger.error(f"Erro ao registrar versão: {e}")
            raise

    # ============================================================
    # MÉTODO PRINCIPAL: run()
    # ============================================================
    def run(self):
        logger.info(f"{'='*60}")
        logger.info(f"🚀 PIPELINE BATCH — REPROCESSAMENTO OTIMIZADO")
        logger.info(f"{'='*60}")
        logger.info(f"📁 Repositório: {self.repo_path}")
        logger.info(f"🏷️  Projeto:    {self.project_name}")
        logger.info(f"🔖 Commit:      {self.commit_hash[:8]}")
        logger.info(f"💬 Mensagem:    {self.commit_msg}")
        logger.info(f"⏰ Início:      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")

        pipeline_start = time.perf_counter()
        log_id = self._create_etl_log()

        try:
            # 1. Detecta arquivos modificados
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
                self.metrics.record("T_ingest", 0.0, "segundos", {
                    "project_name": self.project_name,
                    "commit_hash": self.commit_hash,
                    "status": "no_changes"
                })
                return

            logger.info(f"📄 {len(changed_files)} arquivo(s) para processar")

            # 2. Remove chunks antigos
            with self.metrics.timer("T_delete", metadata={
                "project_name": self.project_name,
                "commit_hash": self.commit_hash,
                "phase": "delete_old"
            }):
                deleted = self._delete_old_chunks(changed_files)
                logger.info(f"🗑️  Chunks removidos: {deleted}")

            # 3. Reprocessa em duas fases (chunking + batch embeddings)
            with self.metrics.memory_tracker("M_peak", metadata={
                "project_name": self.project_name,
                "commit_hash": self.commit_hash,
                "phase": "embed"
            }):
                with self.metrics.timer("T_process", metadata={
                    "project_name": self.project_name,
                    "commit_hash": self.commit_hash,
                    "phase": "chunking_embedding"
                }):
                    chunks_generated, chunks_inserted = self._process_files(changed_files)

            logger.info(f"⚙️  Chunks gerados: {chunks_generated} | Inseridos: {chunks_inserted}")

            # 4. Registra versão
            self._register_version(chunks_inserted)

            # 5. Métricas finais
            elapsed_total = time.perf_counter() - pipeline_start
            self.metrics.calculate_throughput(
                chunks_inserted, elapsed_total,
                self.project_name, phase="full_pipeline"
            )
            self.metrics.record("T_ingest", elapsed_total, "segundos", {
                "project_name": self.project_name,
                "commit_hash": self.commit_hash,
                "files_processed": len(changed_files),
                "chunks_inserted": chunks_inserted,
                "chunks_deleted": deleted
            })

            # 6. Finaliza log
            self._update_etl_log(
                log_id,
                status="completed",
                finished_at=datetime.now(),
                files_processed=len(changed_files),
                chunks_inserted=chunks_inserted,
                chunks_deleted=deleted
            )

            summary = self.metrics.get_summary()
            logger.info(f"{'='*60}")
            logger.info(f"✅ REPROCESSAMENTO CONCLUÍDO")
            logger.info(f"⏰ Término: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"⏱️  Tempo total: {elapsed_total:.1f}s")
            logger.info(f"📊 Métricas:")
            for mtype, stats in summary.items():
                logger.info(f"   • {mtype}: {stats['mean']} {stats['unit']}")
            logger.info(f"{'='*60}")

        except Exception as e:
            logger.error(f"❌ ERRO: {e}", exc_info=True)
            self._update_etl_log(
                log_id,
                status="failed",
                finished_at=datetime.now(),
                error_message=str(e)
            )
            self.metrics.record("T_ingest", -1, "segundos", {
                "project_name": self.project_name,
                "commit_hash": self.commit_hash,
                "status": "failed",
                "error": str(e)
            })
            raise


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline BATCH de reprocessamento de embeddings"
    )
    parser.add_argument("--repo-path", required=True, help="Caminho do repositório git")
    parser.add_argument("--project-name", required=True, help="Nome do projeto")
    parser.add_argument("--commit-hash", default=None, help="Hash do commit")
    parser.add_argument("--commit-msg", default=None, help="Mensagem do commit")
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
