#!/usr/bin/env python3
"""
teste_b_direto.py — Teste B (Proposto) sem protocolo MCP
Chama search_db diretamente via Python e coleta métricas comparáveis.

PRÉ-REQUISITOS:
    pip install psycopg2-binary sentence-transformers torch numpy
    PostgreSQL rodando (docker compose up -d postgres)

USO:
    python teste_b_direto.py --project-name opencv --repo-path ./projects/opencv
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List

import psycopg2
import numpy as np
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("teste_b")


class SimpleMetricsCollector:
    def __init__(self, output_dir: str = "./metrics"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def record(self, metric_type: str, value: float, unit: str, metadata: dict = None):
        record = {
            "timestamp": datetime.now().isoformat(),
            "metric_type": metric_type,
            "value": value,
            "unit": unit,
            "metadata": {**(metadata or {}), "method": "semantic_direct"}
        }
        jsonl_file = self.output_dir / f"metrics_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(jsonl_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')


def count_repository_lines(repo_path: str) -> int:
    code_extensions = {'.cpp', '.hpp', '.h', '.c', '.py', '.js', '.ts'}
    total = 0
    for filepath in Path(repo_path).rglob("*"):
        if filepath.is_file() and filepath.suffix in code_extensions:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    total += len(f.readlines())
            except:
                pass
    return total


class DirectSemanticSearch:
    """Busca semântica direta no PostgreSQL+pgvector."""

    def __init__(self, project_name: str, repo_path: str,
                 db_host="localhost", db_port=5432,
                 db_name="codehelper", db_user="codehelper", db_password="codehelper123"):
        self.project_name = project_name
        self.repo_path = Path(repo_path)
        self.db_config = {
            "host": db_host, "port": db_port, "dbname": db_name,
            "user": db_user, "password": db_password
        }
        self.metrics = SimpleMetricsCollector()
        self._total_lines = None

        # Carrega modelo de embeddings
        logger.info("⚡ Carregando modelo de embeddings...")
        self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        logger.info(f"✅ Modelo carregado: {self.model.get_sentence_embedding_dimension()}d")

    def _get_db_connection(self):
        return psycopg2.connect(**self.db_config)

    def _get_total_lines(self) -> int:
        if self._total_lines is None:
            self._total_lines = count_repository_lines(str(self.repo_path))
            logger.info(f"📏 Total de linhas: {self._total_lines:,}")
        return self._total_lines

    def search(self, query: str, limit: int = 5) -> Dict:
        """Executa busca semântica e coleta métricas."""

        logger.info(f"{'='*50}")
        logger.info(f"🔍 SEMANTIC: {query[:60]}...")

        # 1. Gera embedding da query
        start_total = time.perf_counter()
        start_embed = time.perf_counter()

        query_embedding = self.model.encode(query, convert_to_numpy=True, normalize_embeddings=True)
        embed_time = time.perf_counter() - start_embed

        # 2. Busca no PostgreSQL
        start_db = time.perf_counter()

        conn = self._get_db_connection()
        cursor = conn.cursor()

        # Converte embedding para lista
        embedding_list = query_embedding.tolist()

        cursor.execute("""
            SELECT content, file_path, chunk_index, 
                   1 - (embedding <=> %s::vector) as similarity
            FROM code_vectors
            WHERE metadata->>'project' = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (embedding_list, self.project_name, embedding_list, limit))

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        db_time = time.perf_counter() - start_db
        total_time = time.perf_counter() - start_total

        # 3. Calcula métricas
        returned_lines = sum(len(r[0].split('\n')) for r in results)
        total_lines = self._get_total_lines()
        ssr = (total_lines - returned_lines) / total_lines if total_lines > 0 else 0

        # Verifica se encontrou algo relevante
        query_keywords = [w.lower() for w in query.split() if len(w) > 3]
        found_relevant = any(
            any(kw in r[0].lower() for kw in query_keywords[:3])
            for r in results
        ) if results else False

        # 4. Registra métricas
        self.metrics.record("T_ingest", total_time, "segundos", {
            "project_name": self.project_name,
            "query": query,
            "phase": "full_query"
        })
        self.metrics.record("L_query", total_time * 1000, "ms", {
            "project_name": self.project_name,
            "query": query,
            "chunks_returned": len(results)
        })
        self.metrics.record("SSR", ssr, "proporcao", {
            "project_name": self.project_name,
            "query": query,
            "total_lines": total_lines,
            "returned_lines": returned_lines
        })
        self.metrics.record("P@k", 1.0 if found_relevant else 0.0, "proporcao", {
            "project_name": self.project_name,
            "query": query,
            "chunks_returned": len(results)
        })

        logger.info(f"⏱️  Embedding: {embed_time:.3f}s | DB: {db_time:.3f}s | Total: {total_time:.3f}s")
        logger.info(f"📄 Chunks: {len(results)} | Linhas: {returned_lines} | SSR: {ssr:.4f}")
        logger.info(f"✅ Relevante: {'Sim' if found_relevant else 'Não'}")

        return {
            "query": query,
            "method": "semantic_direct",
            "total_time_sec": round(total_time, 3),
            "embed_time_sec": round(embed_time, 3),
            "db_time_sec": round(db_time, 3),
            "chunks_returned": len(results),
            "lines_returned": returned_lines,
            "total_lines": total_lines,
            "ssr": round(ssr, 6),
            "found_relevant": found_relevant,
            "results_preview": [r[1] for r in results[:3]]
        }


# ============================================================
# 5 CENÁRIOS
# ============================================================
CENARIOS = [
    {
        "id": 1,
        "nome": "Manipulação de Ponteiros e SIMD (cv::resize)",
        "classe": "Otimização de baixo nível",
        "query": "Como cv::resize lida com o alinhamento de ponteiros SIMD e o incremento de memória"
    },
    {
        "id": 2,
        "nome": "Integer Overflow em Convoluções (cv::borderInterpolate)",
        "classe": "Segurança aritmética",
        "query": "cv::borderInterpolate tratamento de estouro de inteiro em bordas de convolução"
    },
    {
        "id": 3,
        "nome": "Concorrência e Multithreading na GUI (highgui/cv::imshow)",
        "classe": "Sincronização de threads",
        "query": "Segurança de threads no gerenciamento de janelas cv::imshow e highgui"
    },
    {
        "id": 4,
        "nome": "Vulnerabilidades em Terceiros (OpenJPEG)",
        "classe": "Segurança de dependências",
        "query": "Tratamento da vulnerabilidade de estouro de buffer do OpenJPEG na decodificação de imagens do OpenCV"
    },
    {
        "id": 5,
        "nome": "Gargalos de Inicialização em Runtime",
        "classe": "Performance de startup",
        "query": "Desempenho do carregamento de bibliotecas em tempo de execução e da inicialização tardia em módulos OpenCV"
    }
]


def main():
    parser = argparse.ArgumentParser(description="Teste B (Proposto) — Busca Semântica Direta")
    parser.add_argument("--project-name", default="opencv", help="Nome do projeto")
    parser.add_argument("--repo-path", default="./projects/opencv", help="Caminho do repo")
    parser.add_argument("--db-host", default="localhost", help="Host PostgreSQL")
    parser.add_argument("--db-password", default="codehelper123", help="Senha PostgreSQL")
    parser.add_argument("--output-dir", default="./ab_results", help="Diretório de saída")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    searcher = DirectSemanticSearch(
        project_name=args.project_name,
        repo_path=args.repo_path,
        db_host=args.db_host,
        db_password=args.db_password
    )

    logger.info(f"{'='*60}")
    logger.info(f"🅱️  TESTE B (PROPOSTO) — 5 CENÁRIOS")
    logger.info(f"{'='*60}")

    results = []

    for scenario in CENARIOS:
        logger.info(f"\n📋 Cenário {scenario['id']}: {scenario['nome']}")

        result = searcher.search(scenario['query'], limit=5)
        result['scenario'] = scenario
        results.append(result)

        # Salva individual
        output_file = output_dir / f"mcp_cenario_{scenario['id']}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        time.sleep(0.5)

    # Relatório consolidado
    report_file = output_dir / f"mcp_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "method": "semantic_direct",
            "scenarios": results
        }, f, indent=2, ensure_ascii=False)

    logger.info(f"\n{'='*60}")
    logger.info(f"✅ TESTE B CONCLUÍDO")
    logger.info(f"📁 Resultados: {args.output_dir}")
    logger.info(f"{'='*60}")

    # Resumo
    print("\n" + "="*60)
    print("📈 RESUMO TESTE B")
    print("="*60)
    for r in results:
        print(f"\nCenário {r['scenario']['id']}: {r['scenario']['nome']}")
        print(f"  ⏱️  Tempo: {r['total_time_sec']}s")
        print(f"  📉 SSR: {r['ssr']}")
        print(f"  📄 Chunks: {r['chunks_returned']}")


if __name__ == "__main__":
    main()
