#!/usr/bin/env python3
"""
run_teste_a_standalone.py — Teste A (Baseline) completo em um arquivo
Não depende de baseline_search_windows.py externo.

Uso:
    python run_teste_a_standalone.py --repo-path ./projects/opencv --project-name opencv
"""

import os
import sys
import json
import time
import argparse
import subprocess
import logging
import platform
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("teste_a")


# ============================================================
# COLETOR DE MÉTRICAS (inline, não depende de metrics_collector.py)
# ============================================================
class SimpleMetricsCollector:
    def __init__(self, output_dir: str = "./metrics"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.records = []

    def record(self, metric_type: str, value: float, unit: str, metadata: dict = None):
        record = {
            "timestamp": datetime.now().isoformat(),
            "metric_type": metric_type,
            "value": value,
            "unit": unit,
            "metadata": metadata or {}
        }
        self.records.append(record)
        # Salva em JSONL imediatamente
        jsonl_file = self.output_dir / f"metrics_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(jsonl_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')

    def calculate_ssr(self, total_lines: int, returned_lines: int, project_name: str, query: str):
        ssr = (total_lines - returned_lines) / total_lines if total_lines > 0 else 0.0
        self.record("SSR", ssr, "proporcao", {
            "project_name": project_name,
            "query": query,
            "total_lines": total_lines,
            "returned_lines": returned_lines
        })
        return ssr


def count_repository_lines(repo_path: str) -> int:
    """Conta linhas de código no repositório."""
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


# ============================================================
# BASELINE SEARCH (inline, não depende de arquivo externo)
# ============================================================
class BaselineSearch:
    def __init__(self, repo_path: str, project_name: str, query: str, metrics: SimpleMetricsCollector):
        self.repo_path = Path(repo_path).resolve()
        self.project_name = project_name
        self.query = query
        self.metrics = metrics
        self._total_lines = None
        self.is_windows = platform.system() == 'Windows'

        if not self.repo_path.exists():
            raise ValueError(f"Repositório não encontrado: {repo_path}")

    def _get_total_lines(self) -> int:
        if self._total_lines is None:
            self._total_lines = count_repository_lines(str(self.repo_path))
            logger.info(f"📏 Total de linhas: {self._total_lines:,}")
        return self._total_lines

    def _extract_keywords(self, query: str) -> List[str]:
        keyword_map = {
            "cv::resize": ["cv::resize", "Resize", "resize", "SIMD", "sse", "avx", "neon"],
            "borderInterpolate": ["borderInterpolate", "border", "interpolate", "overflow", "saturate"],
            "imshow": ["imshow", "highgui", "window", "thread", "mutex", "concurrency"],
            "OpenJPEG": ["OpenJPEG", "jpeg", "jpg", "decoder", "buffer", "vulnerability"],
            "inicialização": ["init", "load", "lazy", "startup", "runtime", "module"]
        }
        for key, terms in keyword_map.items():
            if key.lower() in query.lower():
                return terms
        return [w for w in query.split() if len(w) > 3]

    def _run_search(self, keywords: List[str]) -> Tuple[float, List[Path]]:
        matched_files = set()

        # Detecta ferramenta disponível
        use_rg = False
        use_grep = False
        try:
            subprocess.run(['rg', '--version'], capture_output=True, timeout=2)
            use_rg = True
        except:
            try:
                subprocess.run(['grep', '--version'], capture_output=True, timeout=2)
                use_grep = True
            except:
                pass

        tool = 'rg' if use_rg else ('grep' if use_grep else 'findstr')
        logger.info(f"🔧 Usando: {tool}")

        start_time = time.perf_counter()

        for keyword in keywords:
            if tool == 'rg':
                cmd = ['rg', '-l', '-i', keyword, str(self.repo_path)]
            elif tool == 'grep':
                cmd = ['grep', '-rl', '-i', '--include=*.cpp', '--include=*.hpp', 
                       '--include=*.h', '--include=*.c', '--include=*.py', keyword, str(self.repo_path)]
            else:
                cmd = ['cmd', '/c', 'findstr', '/s', '/i', '/m', keyword, str(self.repo_path / '*.cpp')]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=(tool=='findstr'))
                if result.returncode in (0, 1):
                    for line in result.stdout.strip().split('\n'):
                        line = line.strip()
                        if line and not line.startswith('FINDSTR:'):
                            p = Path(line)
                            if p.exists():
                                matched_files.add(p)
                            else:
                                abs_p = self.repo_path / line
                                if abs_p.exists():
                                    matched_files.add(abs_p)
            except:
                pass

        elapsed = time.perf_counter() - start_time
        return elapsed, sorted(matched_files)

    def _simulate_inspection(self, files: List[Path]) -> Tuple[int, int]:
        total_lines = 0
        found = False
        for filepath in files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    total_lines += len(lines)
                    content = ''.join(lines[:50])
                    if any(kw.lower() in content.lower() for kw in self._extract_keywords(self.query)):
                        found = True
            except:
                pass
        return total_lines, int(found)

    def run(self) -> Dict:
        logger.info(f"{'='*50}")
        logger.info(f"🔍 BASELINE: {self.query[:60]}...")

        keywords = self._extract_keywords(self.query)
        logger.info(f"🎯 Keywords: {keywords}")

        search_time, matched_files = self._run_search(keywords)
        inspect_time_start = time.perf_counter()
        inspected_lines, found_relevant = self._simulate_inspection(matched_files)
        inspect_time = time.perf_counter() - inspect_time_start

        total_time = search_time + inspect_time
        total_lines = self._get_total_lines()
        ssr = (total_lines - inspected_lines) / total_lines if total_lines > 0 else 0.0

        logger.info(f"⏱️  Busca: {search_time:.2f}s | Inspeção: {inspect_time:.3f}s")
        logger.info(f"📄 Arquivos: {len(matched_files)} | Linhas: {inspected_lines:,}")
        logger.info(f"📉 SSR: {ssr:.4f} | Relevante: {'Sim' if found_relevant else 'Não'}")

        # Registra métricas
        self.metrics.record("T_ingest", total_time, "segundos", {
            "project_name": self.project_name,
            "query": self.query,
            "method": "baseline_grep"
        })
        self.metrics.record("L_query", total_time * 1000, "ms", {
            "project_name": self.project_name,
            "query": self.query,
            "method": "baseline_grep",
            "rows_returned": len(matched_files)
        })
        self.metrics.calculate_ssr(total_lines, inspected_lines, self.project_name, self.query)
        self.metrics.record("P@k", 1.0 if found_relevant else 0.0, "proporcao", {
            "project_name": self.project_name,
            "query": self.query,
            "method": "baseline_grep"
        })

        return {
            "query": self.query,
            "keywords": keywords,
            "method": "baseline_grep",
            "total_time_sec": round(total_time, 3),
            "files_matched": len(matched_files),
            "lines_inspected": inspected_lines,
            "total_lines": total_lines,
            "ssr": round(ssr, 6),
            "found_relevant": bool(found_relevant),
            "file_list": [str(f.relative_to(self.repo_path)) for f in matched_files[:10]]
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
    parser = argparse.ArgumentParser(description="Teste A (Baseline) — Standalone")
    parser.add_argument("--repo-path", required=True, help="Caminho do repositório")
    parser.add_argument("--project-name", default="opencv", help="Nome do projeto")
    parser.add_argument("--output-dir", default="./ab_results", help="Diretório de saída")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    metrics = SimpleMetricsCollector(output_dir=str(output_dir / "metrics"))
    results = []

    logger.info(f"{'='*60}")
    logger.info(f"🅰️  TESTE A (BASELINE) — 5 CENÁRIOS")
    logger.info(f"{'='*60}")

    for scenario in CENARIOS:
        logger.info(f"\n📋 Cenário {scenario['id']}: {scenario['nome']}")

        baseline = BaselineSearch(args.repo_path, args.project_name, scenario['query'], metrics)
        result = baseline.run()
        result['scenario'] = scenario
        results.append(result)

        # Salva individual
        output_file = output_dir / f"baseline_cenario_{scenario['id']}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        time.sleep(0.5)

    # Relatório consolidado
    report_file = output_dir / f"baseline_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "method": "baseline_grep",
            "scenarios": results
        }, f, indent=2, ensure_ascii=False)

    logger.info(f"\n{'='*60}")
    logger.info(f"✅ TESTE A CONCLUÍDO")
    logger.info(f"📁 Resultados: {args.output_dir}")
    logger.info(f"{'='*60}")

    # Resumo
    print("\n" + "="*60)
    print("📈 RESUMO TESTE A")
    print("="*60)
    for r in results:
        print(f"\nCenário {r['scenario']['id']}: {r['scenario']['nome']}")
        print(f"  ⏱️  Tempo: {r['total_time_sec']}s")
        print(f"  📉 SSR: {r['ssr']}")
        print(f"  📄 Arquivos: {r['files_matched']}")


if __name__ == "__main__":
    main()
