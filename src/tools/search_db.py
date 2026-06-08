import logging
import os
import time

from src.database.connection import ConectToDataBase
from src.database.etl_process import EmbeddingsETLProcess
from src.utils.system_operations_functions import get_path_root

# ============================================================
# IMPORT DO COLETOR DE MÉTRICAS
# ============================================================
from metrics_collector import MetricsCollector

logger = logging.getLogger("search-db")


class SearchDB:
    """
    Ferramenta de busca semântica com coleta automática de métricas.
    Mede latência (L_query), buffer hit ratio (HR_buf) e calcula SSR.
    """

    def __init__(self, query: str, project_name: str = None, limit: int = 5):
        self.query = query
        self.project_name = project_name
        self.limit = limit
        self.DB_HOST = os.getenv('DB_HOST')
        self.DB_NAME = os.getenv('DB_NAME')
        self.DB_USER = os.getenv('DB_USER')
        self.DB_PASSWORD = os.getenv('DB_PASSWORD', os.getenv('DB_PASSW'))
        self.path_root = get_path_root()

        db = ConectToDataBase(self.DB_HOST, self.DB_PASSWORD, self.DB_NAME, self.DB_USER)
        self.conn = db.create_connection()

        # Inicializa coletor de métricas
        db_config = {
            "host": self.DB_HOST,
            "dbname": self.DB_NAME,
            "user": self.DB_USER,
            "password": self.DB_PASSWORD
        }
        self.metrics = MetricsCollector(db_config=db_config, output_dir="./metrics")

    def _execute(self):
        try:
            embeddings = EmbeddingsETLProcess(self.path_root)
            vector_model = embeddings.generate_embedding()
            vector = vector_model.embed_query(self.query)

            # SQL com medição de latência
            if self.project_name:
                sql = """
                    SELECT content, metadata, 1 - (embedding <=> %s::vector) AS similarity
                    FROM code_vectors
                    WHERE metadata->>'project' = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                """
                params = (vector, self.project_name, vector, self.limit)
            else:
                sql = """
                    SELECT content, metadata, 1 - (embedding <=> %s::vector) AS similarity
                    FROM code_vectors
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                """
                params = (vector, vector, self.limit)

            # ============================================================
            # MEDE LATÊNCIA DA CONSULTA (L_query)
            # ============================================================
            elapsed_ms, rows = self.metrics.measure_query_latency(
                self.conn,
                sql,
                params,
                self.project_name or "all",
                self.limit
            )

            logger.info(f"⚡ Latência da consulta: {elapsed_ms:.2f} ms | {len(rows)} resultados")

            # ============================================================
            # MEDE BUFFER HIT RATIO (HR_buf)
            # ============================================================
            try:
                hr_buf = self._measure_buffer_hit_ratio()
                logger.info(f"💾 Buffer hit ratio: {hr_buf:.2%}")
            except Exception as e:
                logger.warning(f"Não foi possível medir buffer hit ratio: {e}")

            # ============================================================
            # CALCULA SSR (Search Space Reduction)
            # ============================================================
            try:
                ssr = self._calculate_ssr(rows)
                logger.info(f"📉 Search Space Reduction: {ssr:.4f} ({ssr*100:.2f}%)")
            except Exception as e:
                logger.warning(f"Não foi possível calcular SSR: {e}")

            # Formata resultados
            results_txt = []
            total_returned_lines = 0
            for content, metadata, sim in rows:
                src = metadata.get('source', 'unknown')
                results_txt.append(
                    f'FILE: {src}\n'
                    f'SIMILARITY: {sim:.4f}\n'
                    f'CODE_BLOCK: {content}\n'
                    + '-' * 60
                )
                total_returned_lines += len(content.split('\n'))

            return '\n'.join(results_txt) if results_txt else 'Nenhum resultado encontrado.'

        except Exception as e:
            logger.error(f"Erro na busca vetorial: {e}", exc_info=True)
            raise
        finally:
            if self.conn:
                self.conn.close()

    def _measure_buffer_hit_ratio(self) -> float:
        """Calcula HR_buf do PostgreSQL para a tabela code_vectors."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    sum(heap_blks_hit) + sum(idx_blks_hit) as hits,
                    sum(heap_blks_read) + sum(idx_blks_read) as reads
                FROM pg_statio_user_tables
                WHERE relname = 'code_vectors'
            """)
            hits, reads = cur.fetchone()
            hits = hits or 0
            reads = reads or 0
            total = hits + reads
            ratio = hits / total if total > 0 else 0.0

            self.metrics.record("HR_buf", ratio * 100, "%", {
                "hits": hits,
                "reads": reads
            })
            return ratio

    def _calculate_ssr(self, rows) -> float:
        """
        Calcula Search Space Reduction (SSR).
        SSR = (L_total - L_retornadas) / L_total
        """
        # Conta linhas retornadas
        returned_lines = sum(len(content.split('\n')) for content, _, _ in rows)

        # Busca total de linhas do projeto no banco (ou estima)
        with self.conn.cursor() as cur:
            if self.project_name:
                cur.execute("""
                    SELECT COUNT(DISTINCT file_path), 
                           SUM(LENGTH(content) - LENGTH(REPLACE(content, chr(10), '')) + 1)
                    FROM code_vectors
                    WHERE metadata->>'project' = %s
                """, (self.project_name,))
            else:
                cur.execute("""
                    SELECT COUNT(DISTINCT file_path), 
                           SUM(LENGTH(content) - LENGTH(REPLACE(content, chr(10), '')) + 1)
                    FROM code_vectors
                """)

            result = cur.fetchone()
            if result and result[1]:
                total_lines = result[1]
            else:
                total_lines = 2_847_000  # Fallback conservador

        ssr = (total_lines - returned_lines) / total_lines if total_lines > 0 else 0.0

        self.metrics.calculate_ssr(
            total_lines, returned_lines,
            self.project_name or "unknown", self.query
        )
        return ssr

    def get_project_stats(self):
        """Retorna estatísticas com métricas de performance."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*),
                    MAX(metadata->>'commit_hash') as last_commit,
                    MAX(created_at) as last_update
                    FROM code_vectors
                    WHERE metadata->>'project' = %s
                """, (self.project_name,))
                total, last_commit, last_update = cur.fetchone()

                # Mede latência da consulta de stats também
                self.metrics.record("L_query_stats", 0.0, "ms", {
                    "project_name": self.project_name,
                    "query_type": "stats",
                    "total_chunks": total
                })

                return (
                    f"📊 Estatísticas do projeto: {self.project_name}\n"
                    f" Total de chunks: {total}\n"
                    f" Último commit: {last_commit or 'N/A'}\n"
                    f" Última atualização: {last_update or 'N/A'}"
                )
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}", exc_info=True)
            raise
        finally:
            if self.conn:
                self.conn.close()
