import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from metrics_collector import MetricsCollector


# Adiciona o path do projeto para importar módulos
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))


logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("ab_test")


# ============================================================
# 5 CENÁRIOS DE TESTE (conforme Tabela 4 do TCC)
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


class ABTestRunner:
    def __init__(self, repo_path: str, project_name: str, output_dir: str = "./ab_results"):
        self.repo_path = Path(repo_path).resolve()
        self.project_name = project_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.metrics = MetricsCollector(output_dir=str(self.output_dir / "metrics"))

        if not self.repo_path.exists():
            raise ValueError(f"Repositório não encontrado: {repo_path}")

    def run_test_a(self, query: str, scenario_id: int) -> Dict:
        """Executa Teste A (Baseline) via script baseline_search.py"""
        output_file = self.output_dir / f"baseline_scenario_{scenario_id}.json"

        cmd = [
            sys.executable, "baseline_search.py",
            "--repo-path", str(self.repo_path),
            "--project-name", self.project_name,
            "--query", query,
            "--output", str(output_file)
        ]

        logger.info(f"🅰️  Executando Teste A — Cenário {scenario_id}: {query[:50]}...")
        start = time.perf_counter()

        result = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.perf_counter() - start

        if result.returncode != 0:
            logger.error(f"❌ Teste A falhou: {result.stderr}")
            return {"error": result.stderr, "total_time_sec": elapsed}

        # Carrega resultado
        if output_file.exists():
            with open(output_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data["orchestrator_time_sec"] = round(elapsed, 3)
            return data

        return {"error": "Arquivo de saída não gerado", "total_time_sec": elapsed}

    def run_test_b(self, query: str, scenario_id: int) -> Dict:
        """Executa Teste B (Proposto) via MCP Server search_db"""
        # Importa aqui para evitar dependência circular
        from src.tools.search_db import SearchDB

        logger.info(f"🅱️  Executando Teste B — Cenário {scenario_id}: {query[:50]}...")
        start = time.perf_counter()

        try:
            search = SearchDB(query, self.project_name, limit=5)
            result_text = search._execute()
            elapsed = time.perf_counter() - start

            # Extrai métricas do coletor interno do SearchDB
            # (já registradas em JSONL pelo metrics_collector)

            return {
                "query": query,
                "method": "semantic_mcp",
                "total_time_sec": round(elapsed, 3),
                "result_preview": result_text[:500] if result_text else "Nenhum resultado",
                "status": "success"
            }
        except Exception as e:
            elapsed = time.perf_counter() - start
            logger.error(f"❌ Teste B falhou: {e}")
            return {
                "query": query,
                "method": "semantic_mcp",
                "total_time_sec": round(elapsed, 3),
                "error": str(e),
                "status": "failed"
            }

    def run_all(self) -> Dict:
        """Executa todos os 5 cenários nos dois modos e gera relatório."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "repo_path": str(self.repo_path),
            "project_name": self.project_name,
            "scenarios": []
        }

        for scenario in CENARIOS:
            logger.info(f"\n{'='*60}")
            logger.info(f"📋 CENÁRIO {scenario['id']}: {scenario['nome']}")
            logger.info(f"{'='*60}")

            # Teste A
            result_a = self.run_test_a(scenario["query"], scenario["id"])

            # Pequena pausa para não sobrecarregar o banco
            time.sleep(1)

            # Teste B
            result_b = self.run_test_b(scenario["query"], scenario["id"])

            report["scenarios"].append({
                "scenario": scenario,
                "test_a": result_a,
                "test_b": result_b
            })

            logger.info(f"✅ Cenário {scenario['id']} concluído")
            time.sleep(2)

        # Salva relatório completo
        report_file = self.output_dir / f"ab_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"\n{'='*60}")
        logger.info(f"📊 RELATÓRIO A/B COMPLETO SALVO EM: {report_file}")
        logger.info(f"{'='*60}")

        return report


def main():
    parser = argparse.ArgumentParser(description="Orquestrador do Experimento A/B")
    parser.add_argument("--repo-path", required=True, help="Caminho do repositório OpenCV")
    parser.add_argument("--project-name", default="opencv", help="Nome do projeto")
    parser.add_argument("--output-dir", default="./ab_results", help="Diretório de saída")
    args = parser.parse_args()

    runner = ABTestRunner(
        repo_path=args.repo_path,
        project_name=args.project_name,
        output_dir=args.output_dir
    )

    report = runner.run_all()

    # Imprime resumo comparativo
    print("\n" + "="*60)
    print("📈 RESUMO COMPARATIVO — TEMPO TOTAL POR CENÁRIO")
    print("="*60)
    for item in report["scenarios"]:
        s = item["scenario"]
        a = item["test_a"]
        b = item["test_b"]
        print(f"\nCenário {s['id']}: {s['nome']}")
        print(f"  Teste A (Baseline): {a.get('total_time_sec', 'N/A')}s | SSR: {a.get('ssr', 'N/A')}")
        print(f"  Teste B (MCP):      {b.get('total_time_sec', 'N/A')}s")


if __name__ == "__main__":
    main()
