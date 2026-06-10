#!/usr/bin/env python3
"""
analyze_ab.py — Script de análise comparativa A/B
Lê métricas JSONL do Teste A (Baseline) e Teste B (MCP),
gera gráficos comparativos e relatório estatístico.

Uso:
    python analyze_ab.py --metrics-dir ./metrics --output-dir ./ab_analysis
"""

import os
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("analyze_ab")


class ABAnalyzer:
    """
    Analisador de métricas comparativas entre Teste A (Baseline) e Teste B (MCP).
    """

    def __init__(self, metrics_dir: str, output_dir: str = "./ab_analysis"):
        self.metrics_dir = Path(metrics_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.df = None

    def load_metrics(self) -> pd.DataFrame:
        """Carrega todas as métricas JSONL do diretório."""
        records = []

        for jsonl_file in sorted(self.metrics_dir.glob("metrics_*.jsonl")):
            logger.info(f"📂 Carregando: {jsonl_file.name}")
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            record = json.loads(line)
                            # Extrai método dos metadados
                            method = record.get('metadata', {}).get('method', 'unknown')
                            record['method'] = method
                            # Extrai query dos metadados
                            record['query'] = record.get('metadata', {}).get('query', '')
                            # Extrai project_name
                            record['project_name'] = record.get('metadata', {}).get('project_name', '')
                            records.append(record)
                        except json.JSONDecodeError:
                            continue

        self.df = pd.DataFrame(records)
        logger.info(f"✅ {len(records)} registros carregados")

        # Resumo por método
        if not self.df.empty:
            methods = self.df['method'].value_counts()
            logger.info(f"📊 Métodos encontrados:\n{methods}")

        return self.df

    def filter_by_metric(self, metric_type: str) -> pd.DataFrame:
        """Filtra DataFrame por tipo de métrica."""
        if self.df is None:
            raise ValueError("Métricas não carregadas. Execute load_metrics() primeiro.")
        return self.df[self.df['metric_type'] == metric_type].copy()

    def compare_tempo_recuperacao(self) -> Dict:
        """Compara T_ingest (tempo total) entre A e B."""
        df_tempo = self.filter_by_metric('T_ingest')

        baseline = df_tempo[df_tempo['method'] == 'baseline_grep']
        mcp = df_tempo[df_tempo['method'] == 'semantic_mcp']

        result = {
            'baseline_mean_sec': baseline['value'].mean() if not baseline.empty else None,
            'baseline_std_sec': baseline['value'].std() if not baseline.empty else None,
            'baseline_count': len(baseline),
            'mcp_mean_sec': mcp['value'].mean() if not mcp.empty else None,
            'mcp_std_sec': mcp['value'].std() if not mcp.empty else None,
            'mcp_count': len(mcp),
            'speedup': None
        }

        if result['baseline_mean_sec'] and result['mcp_mean_sec']:
            result['speedup'] = result['baseline_mean_sec'] / result['mcp_mean_sec']

        return result

    def compare_ssr(self) -> Dict:
        """Compara SSR entre A e B."""
        df_ssr = self.filter_by_metric('SSR')

        baseline = df_ssr[df_ssr['method'] == 'baseline_grep']
        mcp = df_ssr[df_ssr['method'] == 'semantic_mcp']

        result = {
            'baseline_mean': baseline['value'].mean() if not baseline.empty else None,
            'baseline_min': baseline['value'].min() if not baseline.empty else None,
            'baseline_max': baseline['value'].max() if not baseline.empty else None,
            'mcp_mean': mcp['value'].mean() if not mcp.empty else None,
            'mcp_min': mcp['value'].min() if not mcp.empty else None,
            'mcp_max': mcp['value'].max() if not mcp.empty else None,
        }

        return result

    def plot_comparativo_tempo(self):
        """Gera gráfico de barras comparando tempo de recuperação."""
        df_tempo = self.filter_by_metric('T_ingest')

        if df_tempo.empty:
            logger.warning("⚠️ Sem dados de T_ingest para plotar")
            return

        fig, ax = plt.subplots(figsize=(10, 6))

        # Agrupa por método e calcula estatísticas
        grouped = df_tempo.groupby('method')['value'].agg(['mean', 'std', 'count'])

        methods = grouped.index.tolist()
        means = grouped['mean'].values
        stds = grouped['std'].values

        colors = ['#e74c3c' if 'baseline' in m else '#2ecc71' for m in methods]

        bars = ax.bar(methods, means, yerr=stds, capsize=5, color=colors, alpha=0.8, edgecolor='black')

        ax.set_ylabel('Tempo (segundos)', fontsize=12)
        ax.set_title('Comparação A/B: Tempo de Recuperação de Contexto', fontsize=14, fontweight='bold')
        ax.set_ylim(bottom=0)

        # Adiciona valores nas barras
        for bar, mean, std in zip(bars, means, stds):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + std,
                   f'{mean:.2f}s\n(±{std:.2f})',
                   ha='center', va='bottom', fontsize=10, fontweight='bold')

        # Adiciona speedup se possível
        if len(methods) == 2:
            speedup = means[0] / means[1] if means[1] > 0 else 0
            ax.text(0.5, 0.95, f'Speedup: {speedup:.1f}x',
                   transform=ax.transAxes, ha='center', va='top',
                   bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7),
                   fontsize=12, fontweight='bold')

        plt.tight_layout()
        output_path = self.output_dir / 'comparativo_tempo.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        logger.info(f"📊 Gráfico salvo: {output_path}")
        plt.close()

    def plot_comparativo_ssr(self):
        """Gera gráfico comparando SSR."""
        df_ssr = self.filter_by_metric('SSR')

        if df_ssr.empty:
            logger.warning("⚠️ Sem dados de SSR para plotar")
            return

        fig, ax = plt.subplots(figsize=(10, 6))

        # Agrupa por método
        grouped = df_ssr.groupby('method')['value'].agg(['mean', 'min', 'max'])

        methods = grouped.index.tolist()
        means = grouped['mean'].values
        mins = grouped['min'].values
        maxs = grouped['max'].values

        colors = ['#e74c3c' if 'baseline' in m else '#2ecc71' for m in methods]

        bars = ax.bar(methods, means, color=colors, alpha=0.8, edgecolor='black')

        # Adiciona range (min-max) como linhas de erro
        for i, (bar, mn, mx) in enumerate(zip(bars, mins, maxs)):
            x = bar.get_x() + bar.get_width() / 2
            ax.plot([x, x], [mn, mx], 'k-', linewidth=2)
            ax.plot([x-0.05, x+0.05], [mn, mn], 'k-', linewidth=2)
            ax.plot([x-0.05, x+0.05], [mx, mx], 'k-', linewidth=2)

        ax.set_ylabel('Search Space Reduction (SSR)', fontsize=12)
        ax.set_title('Comparação A/B: Redução do Espaço de Busca', fontsize=14, fontweight='bold')
        ax.set_ylim(0, 1.05)

        # Adiciona valores nas barras
        for bar, mean in zip(bars, means):
            height = bar.get_height()
            pct = mean * 100
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.02,
                   f'{pct:.1f}%\n({mean:.4f})',
                   ha='center', va='bottom', fontsize=10, fontweight='bold')

        plt.tight_layout()
        output_path = self.output_dir / 'comparativo_ssr.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        logger.info(f"📊 Gráfico salvo: {output_path}")
        plt.close()

    def plot_scatter_tempo_vs_ssr(self):
        """Scatter plot: Tempo vs SSR por cenário."""
        df_tempo = self.filter_by_metric('T_ingest')
        df_ssr = self.filter_by_metric('SSR')

        if df_tempo.empty or df_ssr.empty:
            logger.warning("⚠️ Dados insuficientes para scatter plot")
            return

        fig, ax = plt.subplots(figsize=(10, 7))

        for method in df_tempo['method'].unique():
            t_data = df_tempo[df_tempo['method'] == method]
            s_data = df_ssr[df_ssr['method'] == method]

            color = '#e74c3c' if 'baseline' in method else '#2ecc71'
            marker = 'o' if 'baseline' in method else 's'
            label = 'Baseline (grep)' if 'baseline' in method else 'Proposto (MCP)'

            # Junta por query
            merged = pd.merge(
                t_data[['query', 'value']].rename(columns={'value': 'tempo'}),
                s_data[['query', 'value']].rename(columns={'value': 'ssr'}),
                on='query'
            )

            ax.scatter(merged['tempo'], merged['ssr'], 
                      c=color, marker=marker, s=100, alpha=0.7,
                      edgecolors='black', linewidth=1.5, label=label)

            # Adiciona labels dos cenários
            for _, row in merged.iterrows():
                ax.annotate(row['query'][:30] + '...', 
                           (row['tempo'], row['ssr']),
                           fontsize=7, alpha=0.7)

        ax.set_xlabel('Tempo de Recuperação (segundos)', fontsize=12)
        ax.set_ylabel('Search Space Reduction (SSR)', fontsize=12)
        ax.set_title('A/B: Tempo vs. Eficiência de Busca por Cenário', fontsize=14, fontweight='bold')
        ax.legend(fontsize=11)
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        output_path = self.output_dir / 'scatter_tempo_ssr.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        logger.info(f"📊 Gráfico salvo: {output_path}")
        plt.close()

    def generate_report(self) -> str:
        """Gera relatório textual completo."""
        tempo_comp = self.compare_tempo_recuperacao()
        ssr_comp = self.compare_ssr()

        report = f"""
{'='*70}
RELATÓRIO COMPARATIVO A/B — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'='*70}

1. TEMPO DE RECUPERAÇÃO (T_ingest)
   ──────────────────────────────────────────────────────────────────
   Baseline (grep manual):
     • Média: {tempo_comp['baseline_mean_sec']:.3f}s (±{tempo_comp['baseline_std_sec']:.3f}s)
     • Execuções: {tempo_comp['baseline_count']}

   Proposto (MCP semantic):
     • Média: {tempo_comp['mcp_mean_sec']:.3f}s (±{tempo_comp['mcp_std_sec']:.3f}s)
     • Execuções: {tempo_comp['mcp_count']}

   Speedup: {tempo_comp['speedup']:.2f}x
   (Quanto maior, mais rápido o MCP em relação ao grep)

2. SEARCH SPACE REDUCTION (SSR)
   ──────────────────────────────────────────────────────────────────
   Baseline (grep manual):
     • Média: {ssr_comp['baseline_mean']:.4f} ({ssr_comp['baseline_mean']*100:.2f}%)
     • Range: [{ssr_comp['baseline_min']:.4f}, {ssr_comp['baseline_max']:.4f}]

   Proposto (MCP semantic):
     • Média: {ssr_comp['mcp_mean']:.4f} ({ssr_comp['mcp_mean']*100:.2f}%)
     • Range: [{ssr_comp['mcp_min']:.4f}, {ssr_comp['mcp_max']:.4f}]

   Diferença: {(ssr_comp['mcp_mean'] - ssr_comp['baseline_mean'])*100:.2f} pontos percentuais
   a favor do MCP.

3. INTERPRETAÇÃO
   ──────────────────────────────────────────────────────────────────
   O Teste B (MCP) demonstra vantagem quando:
   • Speedup > 1 (MCP mais rápido que grep)
   • SSR_mcp >> SSR_baseline (MCP filtra muito mais código irrelevante)

   Um SSR de ~0.995 no MCP significa que o desenvolvedor inspeciona
   apenas 0.5% do código total, vs. {ssr_comp['baseline_mean']*100:.1f}% no baseline.

{'='*70}
"""

        # Salva relatório
        report_path = self.output_dir / 'relatorio_ab.txt'
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"📄 Relatório salvo: {report_path}")
        return report

    def run_full_analysis(self):
        """Executa análise completa: carrega, plota e gera relatório."""
        logger.info(f"{'='*60}")
        logger.info("🔬 ANÁLISE COMPARATIVA A/B — INICIANDO")
        logger.info(f"{'='*60}")

        self.load_metrics()

        if self.df.empty:
            logger.error("❌ Nenhuma métrica encontrada. Verifique o diretório.")
            return

        self.plot_comparativo_tempo()
        self.plot_comparativo_ssr()
        self.plot_scatter_tempo_vs_ssr()

        report = self.generate_report()
        print("\n" + report)

        logger.info(f"{'='*60}")
        logger.info("✅ ANÁLISE CONCLUÍDA")
        logger.info(f"📁 Resultados em: {self.output_dir.absolute()}")
        logger.info(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Análise comparativa A/B do experimento")
    parser.add_argument("--metrics-dir", default="./metrics", help="Diretório com arquivos JSONL de métricas")
    parser.add_argument("--output-dir", default="./ab_analysis", help="Diretório de saída para gráficos e relatório")
    args = parser.parse_args()

    analyzer = ABAnalyzer(metrics_dir=args.metrics_dir, output_dir=args.output_dir)
    analyzer.run_full_analysis()


if __name__ == "__main__":
    main()
