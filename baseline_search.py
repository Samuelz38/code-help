import os
import sys
import time
import json
import argparse
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Reutiliza o coletor de métricas do projeto
from metrics_collector import MetricsCollector, count_repository_lines

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("baseline")


class BaselineSearch:
    """
    Implementação do Cenário A (Baseline): busca textual via grep + navegação manual.
    """

    def __init__(self, repo_path: str, project_name: str, query: str):
        self.repo_path = Path(repo_path).resolve()
        self.project_name = project_name
        self.query = query
        self.metrics = MetricsCollector(output_dir="./metrics")
        self._total_lines = None

        if not self.repo_path.exists():
            raise ValueError(f"Repositório não encontrado: {repo_path}")

    def _get_total_lines(self) -> int:
        """Cache do total de linhas do repositório (para SSR)."""
        if self._total_lines is None:
            self._total_lines = count_repository_lines(str(self.repo_path))
            logger.info(f"📏 Total de linhas no repositório: {self._total_lines:,}")
        return self._total_lines

    def _extract_keywords(self, query: str) -> List[str]:
        """
        Extrai palavras-chave técnicas da query em linguagem natural.
        Exemplo: "Como cv::resize lida com o alinhamento de ponteiros SIMD"
        -> ['cv::resize', 'SIMD', 'align']
        """
        # Mapeamento manual das 5 queries do experimento para termos de grep
        keyword_map = {
            "cv::resize": ["cv::resize", "Resize", "resize", "SIMD", "sse", "avx", "neon"],
            "borderInterpolate": ["borderInterpolate", "border", "interpolate", "overflow", "saturate"],
            "imshow": ["imshow", "highgui", "window", "thread", "mutex", "concurrency"],
            "OpenJPEG": ["OpenJPEG", "jpeg", "jpg", "decoder", "buffer", "vulnerability"],
            "inicialização": ["init", "load", "lazy", "startup", "runtime", "module"]
        }

        # Tenta match direto
        for key, terms in keyword_map.items():
            if key.lower() in query.lower():
                return terms

        # Fallback: split simples
        return [w for w in query.split() if len(w) > 3]

    def _run_grep(self, keywords: List[str]) -> Tuple[float, List[Path]]:
        """
        Executa grep (ou ripgrep se disponível) no repositório.
        Retorna: (tempo_segundos, lista_de_arquivos_encontrados)
        """
        code_extensions = ['*.cpp', '*.hpp', '*.h', '*.c', '*.py', '*.js', '*.ts']
        matched_files = set()

        start_time = time.perf_counter()

        # Preferência por ripgrep (rg) se disponível — mais rápido
        use_rg = subprocess.run(['which', 'rg'], capture_output=True).returncode == 0

        for keyword in keywords:
            if use_rg:
                cmd = [
                    'rg', '-l', '-i', '--type-add', 'code:*.{cpp,hpp,h,c,py,js,ts}',
                    '-tcode', keyword, str(self.repo_path)
                ]
            else:
                # Fallback para grep tradicional
                cmd = [
                    'grep', '-rl', '-i', '--include=*.cpp', '--include=*.hpp',
                    '--include=*.h', '--include=*.c', '--include=*.py',
                    '--include=*.js', '--include=*.ts',
                    keyword, str(self.repo_path)
                ]

            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120
                )
                if result.returncode in (0, 1):  # 0 = matches, 1 = no matches
                    for line in result.stdout.strip().split('\n'):
                        if line:
                            matched_files.add(Path(line))
            except Exception as e:
                logger.warning(f"Erro ao executar grep para '{keyword}': {e}")

        elapsed = time.perf_counter() - start_time
        return elapsed, sorted(matched_files)

    def _simulate_manual_inspection(self, files: List[Path]) -> Tuple[int, int]:
        """
        Simula a navegação manual: conta linhas inspecionadas e verifica
        se algum arquivo contém de fato a resposta (precisão binária).

        Retorna: (linhas_inspecionadas, encontrou_resposta_bool)
        """
        total_inspected_lines = 0
        found_relevant = False

        # Simula: desenvolvedor abre cada arquivo retornado pelo grep
        # e inspeciona até encontrar a função relevante (ou desistir)
        for filepath in files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    total_inspected_lines += len(lines)

                    # Heurística: considera "relevante" se o arquivo menciona
                    # termos-chave da query nas primeiras 50 linhas ou em comentários
                    content = ''.join(lines[:50])
                    if any(kw.lower() in content.lower() for kw in self._extract_keywords(self.query)):
                        found_relevant = True
            except Exception:
                pass

        return total_inspected_lines, int(found_relevant)

    def run(self) -> Dict:
        """
        Executa o pipeline completo do Teste A e retorna métricas.
        """
        logger.info(f"{'='*60}")
        logger.info(f"🔍 TESTE A (BASELINE) — Busca Textual via Grep")
        logger.info(f"{'='*60}")
        logger.info(f"📁 Repositório: {self.repo_path}")
        logger.info(f"🔍 Query: {self.query}")

        # 1. Extrai keywords
        keywords = self._extract_keywords(self.query)
        logger.info(f"🎯 Keywords extraídas: {keywords}")

        # 2. Executa busca grep (mede tempo)
        grep_time, matched_files = self._run_grep(keywords)
        logger.info(f"⏱️ Tempo de busca grep: {grep_time:.2f}s | Arquivos: {len(matched_files)}")

        # 3. Simula inspeção manual
        inspect_time_start = time.perf_counter()
        inspected_lines, found_relevant = self._simulate_manual_inspection(matched_files)
        inspect_time = time.perf_counter() - inspect_time_start

        total_time = grep_time + inspect_time
        logger.info(f"📄 Linhas inspecionadas: {inspected_lines:,}")
        logger.info(f"✅ Resposta relevante encontrada: {'Sim' if found_relevant else 'Não'}")
        logger.info(f"⏱️ Tempo total (busca + inspeção): {total_time:.2f}s")

        # 4. Calcula SSR (Search Space Reduction) — no baseline, SSR = 0
        # porque o desenvolvedor inspecionou tudo manualmente
        total_lines = self._get_total_lines()
        ssr = (total_lines - inspected_lines) / total_lines if total_lines > 0 else 0.0
        logger.info(f"📉 SSR: {ssr:.4f} ({ssr*100:.2f}%)")

        # 5. Registra métricas no mesmo formato do Teste B
        self.metrics.record("T_ingest", total_time, "segundos", {
            "project_name": self.project_name,
            "query": self.query,
            "method": "baseline_grep",
            "phase": "full_search"
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
            "method": "baseline_grep",
            "files_matched": len(matched_files)
        })

        # Retorna resumo
        return {
            "query": self.query,
            "keywords": keywords,
            "method": "baseline_grep",
            "grep_time_sec": round(grep_time, 3),
            "inspection_time_sec": round(inspect_time, 3),
            "total_time_sec": round(total_time, 3),
            "files_matched": len(matched_files),
            "lines_inspected": inspected_lines,
            "total_lines": total_lines,
            "ssr": round(ssr, 6),
            "found_relevant": bool(found_relevant),
            "file_list": [str(f.relative_to(self.repo_path)) for f in matched_files[:10]]
        }


def main():
    parser = argparse.ArgumentParser(
        description="Teste A (Baseline) — Busca textual via grep + navegação manual"
    )
    parser.add_argument("--repo-path", required=True, help="Caminho do repositório OpenCV")
    parser.add_argument("--project-name", default="opencv", help="Nome do projeto")
    parser.add_argument("--query", required=True, help="Query em linguagem natural")
    parser.add_argument("--output", default="baseline_result.json", help="Arquivo de saída JSON")
    args = parser.parse_args()

    baseline = BaselineSearch(
        repo_path=args.repo_path,
        project_name=args.project_name,
        query=args.query
    )

    result = baseline.run()

    # Salva resultado em JSON para análise comparativa
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    logger.info(f"\n✅ Resultado salvo em: {args.output}")
    logger.info(f"📊 Resumo: {json.dumps(result, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
