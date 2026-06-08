import time
import psutil
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("metrics")


class MetricsCollector:
    """
    Coletor de métricas de performance do pipeline ETL e RAG.
    Persiste dados em arquivo JSONL e opcionalmente no PostgreSQL.
    """

    def __init__(self, db_config: Optional[Dict] = None, output_dir: str = "./metrics"):
        self.db_config = db_config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.metrics_file = self.output_dir / f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        self.metrics_log_file = self.log_dir / "metrics.log"
        self._process = psutil.Process()
        self._baseline_memory = self._process.memory_info().rss

    def _get_db_connection(self):
        """Estabelece conexão com PostgreSQL para métricas."""
        if not self.db_config:
            return None
        return psycopg2.connect(
            host=self.db_config.get("host", "localhost"),
            database=self.db_config.get("dbname", "codehelper"),
            user=self.db_config.get("user", "codehelper"),
            password=self.db_config.get("password", "codehelper123")
        )

    def record(self, metric_type: str, value: float, unit: str, 
               metadata: Optional[Dict] = None) -> Dict:
        """
        Registra uma métrica individual.

        Args:
            metric_type: Tipo da métrica (T_ingest, L_query, TH_chunk, etc.)
            value: Valor numérico medido
            unit: Unidade (segundos, ms, chunks/s, MB, %)
            metadata: Dados adicionais (commit_hash, project_name, query, etc.)

        Returns:
            Dict com a métrica registrada
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "metric_type": metric_type,
            "value": round(value, 6),
            "unit": unit,
            "metadata": metadata or {}
        }

        # Persiste em arquivo JSONL (append-only, thread-safe)
        with open(self.metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Grava também em log de métricas para centralização via Loki/Promtail
        with open(self.metrics_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.debug(f"Métrica registrada: {metric_type}={value} {unit}")
        return record

    @contextmanager
    def timer(self, metric_type: str, unit: str = "segundos", 
              metadata: Optional[Dict] = None):
        """
        Context manager para medir tempo de execução de blocos de código.

        Uso:
            with collector.timer("T_ingest", metadata={"project": "opencv"}):
                reprocessor.run()
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.record(metric_type, elapsed, unit, metadata)

    @contextmanager
    def memory_tracker(self, metric_type: str = "M_peak", 
                       metadata: Optional[Dict] = None):
        """
        Context manager para medir pico de memória durante execução.

        Uso:
            with collector.memory_tracker(metadata={"phase": "embed"}):
                generate_embeddings()
        """
        start_rss = self._process.memory_info().rss
        try:
            yield
        finally:
            current_rss = self._process.memory_info().rss
            peak_mb = max(0, current_rss - start_rss) / (1024 * 1024)
            self.record(metric_type, peak_mb, "MB", metadata)

    def measure_query_latency(self, conn, query_sql: str, params: Tuple,
                               project_name: str, limit: int) -> Tuple[float, int]:
        """
        Mede latência de uma consulta vetorial no PostgreSQL.

        Returns:
            (latencia_ms, num_rows)
        """
        start = time.perf_counter()
        with conn.cursor() as cur:
            cur.execute(query_sql, params)
            rows = cur.fetchall()
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.record(
            "L_query", elapsed_ms, "ms",
            metadata={
                "project_name": project_name,
                "limit": limit,
                "rows_returned": len(rows),
                "query_preview": query_sql[:100]
            }
        )
        return elapsed_ms, rows

    def measure_buffer_hit_ratio(self, conn) -> float:
        """
        Calcula taxa de acerto no buffer pool do PostgreSQL.

        Returns:
            HR_buf (0.0 a 1.0)
        """
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    sum(heap_blks_hit) + sum(idx_blks_hit) as hits,
                    sum(heap_blks_read) + sum(idx_blks_read) as reads
                FROM pg_statio_user_tables
                WHERE relname = 'code_vectors'
            """)
            hits, reads = cur.fetchone()
            if hits is None:
                hits = 0
            if reads is None:
                reads = 0

            total = hits + reads
            ratio = hits / total if total > 0 else 0.0

            self.record("HR_buf", ratio * 100, "%", metadata={"hits": hits, "reads": reads})
            return ratio

    def calculate_ssr(self, total_lines: int, returned_lines: int,
                      project_name: str, query: str) -> float:
        """
        Calcula Search Space Reduction (SSR).

        SSR = (L_total - L_retornadas) / L_total

        Args:
            total_lines: Total de linhas do repositório
            returned_lines: Linhas dos chunks retornados
            project_name: Nome do projeto
            query: Query que gerou a busca

        Returns:
            SSR (0.0 a 1.0)
        """
        ssr = (total_lines - returned_lines) / total_lines if total_lines > 0 else 0.0

        self.record(
            "SSR", ssr, "proporcao",
            metadata={
                "project_name": project_name,
                "query": query,
                "total_lines": total_lines,
                "returned_lines": returned_lines
            }
        )
        return ssr

    def calculate_throughput(self, chunks_count: int, elapsed_seconds: float,
                            project_name: str, phase: str = "ingest") -> float:
        """
        Calcula throughput de chunks processados.

        TH_chunk = chunks / segundos
        """
        th = chunks_count / elapsed_seconds if elapsed_seconds > 0 else 0.0

        self.record(
            "TH_chunk", th, "chunks/segundo",
            metadata={
                "project_name": project_name,
                "phase": phase,
                "chunks_count": chunks_count,
                "elapsed_seconds": elapsed_seconds
            }
        )
        return th

    def get_summary(self) -> Dict:
        """
        Retorna resumo estatístico de todas as métricas coletadas.
        """
        if not self.metrics_file.exists():
            return {}

        metrics_by_type = {}
        with open(self.metrics_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    mtype = record["metric_type"]
                    if mtype not in metrics_by_type:
                        metrics_by_type[mtype] = []
                    metrics_by_type[mtype].append(record["value"])

        summary = {}
        for mtype, values in metrics_by_type.items():
            if values:
                summary[mtype] = {
                    "count": len(values),
                    "min": round(min(values), 4),
                    "max": round(max(values), 4),
                    "mean": round(sum(values) / len(values), 4),
                    "unit": self._get_unit_for_type(mtype)
                }

        return summary

    def _get_unit_for_type(self, metric_type: str) -> str:
        """Retorna unidade padrão para cada tipo de métrica."""
        units = {
            "T_ingest": "segundos",
            "L_query": "ms",
            "TH_chunk": "chunks/segundo",
            "M_peak": "MB",
            "HR_buf": "%",
            "SSR": "proporcao",
            "P@k": "proporcao",
            "E_token": "tokens"
        }
        return units.get(metric_type, "unidade")

    def export_to_csv(self, output_path: Optional[str] = None) -> str:
        """
        Exporta métricas para CSV (para análise no Excel/R/Python).
        """
        import csv

        output_path = output_path or str(self.output_dir / "metrics_export.csv")

        with open(self.metrics_file, "r", encoding="utf-8") as f_in, \
             open(output_path, "w", newline="", encoding="utf-8") as f_out:

            writer = None
            for line in f_in:
                if line.strip():
                    record = json.loads(line)
                    flat_record = {
                        "timestamp": record["timestamp"],
                        "metric_type": record["metric_type"],
                        "value": record["value"],
                        "unit": record["unit"],
                    }
                    # Flatten metadata
                    for k, v in record.get("metadata", {}).items():
                        flat_record[f"meta_{k}"] = v

                    if writer is None:
                        writer = csv.DictWriter(f_out, fieldnames=flat_record.keys())
                        writer.writeheader()
                    writer.writerow(flat_record)

        logger.info(f"Métricas exportadas para: {output_path}")
        return output_path


# ============================================================
# Função utilitária: contar linhas de código do repositório
# ============================================================

def count_repository_lines(repo_path: str, extensions: List[str] = None) -> int:
    """
    Conta total de linhas de código em um repositório.

    Usado para cálculo do SSR.
    """
    if extensions is None:
        extensions = ['.cpp', '.hpp', '.h', '.c', '.py', '.js', '.ts']

    total = 0
    repo = Path(repo_path)
    for ext in extensions:
        for filepath in repo.rglob(f"*{ext}"):
            if filepath.is_file():
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        total += len(f.readlines())
                except Exception:
                    pass

    return total


if __name__ == "__main__":
    # Teste básico
    collector = MetricsCollector()

    # Simula medição
    with collector.timer("T_ingest", metadata={"project": "test"}):
        time.sleep(0.1)

    collector.record("L_query", 45.2, "ms", {"query": "test"})
    collector.calculate_ssr(2_847_000, 8_500, "opencv", "cv::resize SIMD")

    print("Resumo:", json.dumps(collector.get_summary(), indent=2, ensure_ascii=False))
