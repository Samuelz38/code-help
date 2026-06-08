import json
import argparse
import statistics
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.patches import FancyBboxPatch

# Configuração visual
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette('husl')
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 11


class MetricsAnalyzer:
    """
    Analisador de métricas do pipeline CodeHelp.
    """

    def __init__(self, input_file: str, output_dir: str = "./tcc_graficos"):
        self.input_file = Path(input_file)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.df = None

    def load(self) -> pd.DataFrame:
        """Carrega métricas do arquivo JSONL."""
        records = []
        with open(self.input_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))

        self.df = pd.DataFrame(records)

        # Parse timestamp
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])

        # Extrair metadata como colunas separadas
        metadata_cols = []
        for idx, row in self.df.iterrows():
            meta = row.get('metadata', {})
            for key, val in meta.items():
                col_name = f"meta_{key}"
                if col_name not in self.df.columns:
                    self.df[col_name] = None
                self.df.at[idx, col_name] = val

        print(f"✅ Carregadas {len(self.df)} métricas de {self.input_file}")
        print(f"📊 Tipos de métricas: {self.df['metric_type'].unique().tolist()}")
        return self.df

    def summary(self) -> Dict[str, Any]:
        """Gera resumo estatístico por tipo de métrica."""
        if self.df is None:
            raise ValueError("Execute load() primeiro")

        summary = {}
        for mtype in self.df['metric_type'].unique():
            subset = self.df[self.df['metric_type'] == mtype]['value']
            if len(subset) > 0:
                summary[mtype] = {
                    'count': len(subset),
                    'min': round(subset.min(), 4),
                    'max': round(subset.max(), 4),
                    'mean': round(subset.mean(), 4),
                    'median': round(subset.median(), 4),
                    'std': round(subset.std(), 4) if len(subset) > 1 else 0,
                    'unit': self.df[self.df['metric_type'] == mtype]['unit'].iloc[0]
                }

        return summary

    def print_summary(self):
        """Imprime resumo formatado no console."""
        summary = self.summary()
        print("" + "="*70)
        print("RESUMO ESTATÍSTICO DAS MÉTRICAS")
        print("="*70)
        for mtype, stats in summary.items():
            print(f"📊 {mtype} ({stats['unit']}) - {stats['count']} medições:")
            print(f"   Mín: {stats['min']:<12} Máx: {stats['max']:<12}")
            print(f"   Méd: {stats['mean']:<12} Med: {stats['median']:<12}")
            print(f"   Std: {stats['std']:<12}")
        print("="*70)

    # ============================================================
    # GRÁFICO 1: Baseline - Indexação Inicial
    # ============================================================
    def plot_baseline(self):
        """Gráfico de barras com métricas da indexação inicial."""
        # Filtra métricas de baseline (T_ingest com status != failed)
        baseline = self.df[
            (self.df['metric_type'] == 'T_ingest') & 
            (self.df['meta_status'] != 'failed')
        ]

        if len(baseline) == 0:
            print("⚠️ Nenhuma métrica de baseline encontrada")
            return

        # Pega a última medição de baseline (indexação inicial completa)
        last = baseline.iloc[-1]

        # Busca métricas relacionadas na mesma execução
        commit = last.get('meta_commit_hash', 'unknown')
        related = self.df[
            (self.df['meta_commit_hash'] == commit) |
            (self.df['metric_type'].isin(['TH_chunk', 'M_peak']))
        ]

        # Monta dados para o gráfico
        metrics_data = {
            'Tempo Total (s)': last['value'] if last['unit'] == 'segundos' else 0,
            'Chunks Gerados': related[related['metric_type'] == 'TH_chunk']['meta_chunks_count'].max() if 'meta_chunks_count' in related.columns else 0,
            'Memória Pico (MB)': related[related['metric_type'] == 'M_peak']['value'].max() if len(related[related['metric_type'] == 'M_peak']) > 0 else 0,
        }

        fig, ax = plt.subplots(figsize=(12, 6))
        colors = ['#E17055', '#FDCB6E', '#55EFC4']
        bars = ax.barh(list(metrics_data.keys()), list(metrics_data.values()), 
                       color=colors, edgecolor='black')

        for bar, (label, val) in zip(bars, metrics_data.items()):
            unit = 's' if 'Tempo' in label else ('chunks' if 'Chunks' in label else 'MB')
            ax.text(bar.get_width() + max(metrics_data.values())*0.02, 
                   bar.get_y() + bar.get_height()/2, 
                   f'{val:.0f} {unit}', va='center', fontsize=10, weight='bold')

        ax.set_title('Baseline - Indexação Inicial do OpenCV', fontsize=14, weight='bold')
        ax.set_xlabel('Valor')
        plt.tight_layout()

        output_path = self.output_dir / 'grafico_baseline_real.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"📊 Gráfico baseline salvo: {output_path}")

    # ============================================================
    # GRÁFICO 2: Latência de Consultas ao Longo do Tempo
    # ============================================================
    def plot_latency_timeline(self):
        """Série temporal da latência de consultas (L_query)."""
        queries = self.df[self.df['metric_type'] == 'L_query'].copy()

        if len(queries) == 0:
            print("⚠️ Nenhuma métrica de latência encontrada")
            return

        queries = queries.sort_values('timestamp')

        fig, ax = plt.subplots(figsize=(14, 5))
        ax.plot(queries['timestamp'], queries['value'], 'o-', 
                color='#E17055', linewidth=2, markersize=6, label='Latência observada')
        ax.fill_between(queries['timestamp'], queries['value'], alpha=0.3, color='#E17055')

        # Linha de média
        mean_lat = queries['value'].mean()
        ax.axhline(y=mean_lat, color='green', linestyle='--', 
                  label=f'Média: {mean_lat:.1f} ms')

        ax.set_xlabel('Timestamp')
        ax.set_ylabel('Latência (ms)')
        ax.set_title('Latência de Busca Vetorial ao Longo do Tempo', fontsize=14, weight='bold')
        ax.legend()
        ax.tick_params(axis='x', rotation=45)

        plt.tight_layout()
        output_path = self.output_dir / 'grafico_latencia_timeline.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"📊 Gráfico latência salvo: {output_path}")

    # ============================================================
    # GRÁFICO 3: Throughput por Fase do Pipeline
    # ============================================================
    def plot_throughput(self):
        """Compara throughput entre fases do pipeline."""
        th_data = self.df[self.df['metric_type'] == 'TH_chunk']

        if len(th_data) == 0:
            print("⚠️ Nenhuma métrica de throughput encontrada")
            return

        phases = th_data['meta_phase'].unique() if 'meta_phase' in th_data.columns else ['unknown']

        fig, ax = plt.subplots(figsize=(10, 6))
        colors = ['#55EFC4', '#FDCB6E', '#E17055', '#74B9FF']

        for i, phase in enumerate(phases):
            phase_data = th_data[th_data['meta_phase'] == phase]['value']
            if len(phase_data) > 0:
                ax.bar(phase, phase_data.mean(), color=colors[i % len(colors)], 
                       edgecolor='black', alpha=0.9)
                ax.text(phase, phase_data.mean() + 0.5, 
                       f'{phase_data.mean():.1f}', ha='center', va='bottom', 
                       fontsize=11, weight='bold')

        ax.set_ylabel('Chunks / segundo')
        ax.set_title('Throughput por Fase do Pipeline ETL', fontsize=14, weight='bold')
        plt.tight_layout()

        output_path = self.output_dir / 'grafico_throughput.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"📊 Gráfico throughput salvo: {output_path}")

    # ============================================================
    # GRÁFICO 4: Search Space Reduction (SSR)
    # ============================================================
    def plot_ssr(self):
        """Distribuição do SSR por query."""
        ssr_data = self.df[self.df['metric_type'] == 'SSR'].copy()

        if len(ssr_data) == 0:
            print("⚠️ Nenhuma métrica SSR encontrada")
            return

        ssr_data['ssr_pct'] = ssr_data['value'] * 100

        fig, ax = plt.subplots(figsize=(12, 6))

        # Barras horizontais por query
        queries = ssr_data['meta_query'].str[:40] if 'meta_query' in ssr_data.columns else ssr_data.index.astype(str)
        colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(ssr_data)))

        bars = ax.barh(range(len(ssr_data)), ssr_data['ssr_pct'], color=colors, edgecolor='black')
        ax.set_yticks(range(len(ssr_data)))
        ax.set_yticklabels(queries, fontsize=9)
        ax.set_xlabel('SSR (%)')
        ax.set_title('Search Space Reduction por Query', fontsize=14, weight='bold')
        ax.set_xlim(0, 100)

        # Adiciona valores nas barras
        for i, (bar, val) in enumerate(zip(bars, ssr_data['ssr_pct'])):
            ax.text(val + 1, bar.get_y() + bar.get_height()/2, 
                   f'{val:.2f}%', va='center', fontsize=9, weight='bold')

        # Linha de média
        mean_ssr = ssr_data['ssr_pct'].mean()
        ax.axvline(x=mean_ssr, color='red', linestyle='--', linewidth=2, 
                  label=f'Média: {mean_ssr:.2f}%')
        ax.legend()

        plt.tight_layout()
        output_path = self.output_dir / 'grafico_ssr.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"📊 Gráfico SSR salvo: {output_path}")

    # ============================================================
    # GRÁFICO 5: Buffer Hit Ratio ao Longo do Tempo
    # ============================================================
    def plot_buffer_ratio(self):
        """Evolução da taxa de acerto no buffer pool."""
        hr_data = self.df[self.df['metric_type'] == 'HR_buf'].copy()

        if len(hr_data) == 0:
            print("⚠️ Nenhuma métrica HR_buf encontrada")
            return

        hr_data = hr_data.sort_values('timestamp')

        fig, ax = plt.subplots(figsize=(14, 5))
        ax.plot(hr_data['timestamp'], hr_data['value'], 's-', 
                color='#74B9FF', linewidth=2, markersize=6, label='HR_buf')
        ax.fill_between(hr_data['timestamp'], hr_data['value'], alpha=0.3, color='#74B9FF')

        ax.set_ylim(0, 100)
        ax.set_xlabel('Timestamp')
        ax.set_ylabel('Taxa de Acerto (%)')
        ax.set_title('Buffer Hit Ratio do PostgreSQL (pgvector)', fontsize=14, weight='bold')
        ax.legend()
        ax.tick_params(axis='x', rotation=45)

        plt.tight_layout()
        output_path = self.output_dir / 'grafico_buffer_ratio.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"📊 Gráfico buffer ratio salvo: {output_path}")

    # ============================================================
    # GRÁFICO 6: Comparação de Consumo de Memória
    # ============================================================
    def plot_memory(self):
        """Pico de memória por fase do pipeline."""
        mem_data = self.df[self.df['metric_type'] == 'M_peak'].copy()

        if len(mem_data) == 0:
            print("⚠️ Nenhuma métrica de memória encontrada")
            return

        phases = mem_data['meta_phase'].unique() if 'meta_phase' in mem_data.columns else ['unknown']

        fig, ax = plt.subplots(figsize=(10, 6))
        colors = ['#E17055', '#FDCB6E', '#55EFC4']

        for i, phase in enumerate(phases):
            phase_data = mem_data[mem_data['meta_phase'] == phase]['value']
            if len(phase_data) > 0:
                ax.bar(phase, phase_data.mean(), color=colors[i % len(colors)], 
                       edgecolor='black', alpha=0.9)
                ax.text(phase, phase_data.mean() + 50, 
                       f'{phase_data.mean():.0f} MB', ha='center', va='bottom', 
                       fontsize=10, weight='bold')

        ax.set_ylabel('Memória (MB)')
        ax.set_title('Pico de Memória RAM por Fase', fontsize=14, weight='bold')
        plt.tight_layout()

        output_path = self.output_dir / 'grafico_memoria.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"📊 Gráfico memória salvo: {output_path}")

    # ============================================================
    # GRÁFICO 7: Dashboard Consolidado
    # ============================================================
    def plot_dashboard(self):
        """Dashboard consolidado com todas as métricas principais."""
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle('Dashboard de Métricas - CodeHelper', fontsize=16, weight='bold')

        # 1. Latência
        queries = self.df[self.df['metric_type'] == 'L_query']
        if len(queries) > 0:
            axes[0,0].hist(queries['value'], bins=20, color='#E17055', edgecolor='black', alpha=0.8)
            axes[0,0].axvline(queries['value'].mean(), color='green', linestyle='--', linewidth=2)
            axes[0,0].set_title('Distribuição da Latência (ms)')
            axes[0,0].set_xlabel('ms')

        # 2. Throughput
        th = self.df[self.df['metric_type'] == 'TH_chunk']
        if len(th) > 0:
            axes[0,1].plot(th['timestamp'], th['value'], 'o-', color='#55EFC4')
            axes[0,1].set_title('Throughput (chunks/s)')
            axes[0,1].tick_params(axis='x', rotation=45)

        # 3. SSR
        ssr = self.df[self.df['metric_type'] == 'SSR']
        if len(ssr) > 0:
            axes[0,2].scatter(range(len(ssr)), ssr['value']*100, color='#74B9FF', s=100, edgecolor='black')
            axes[0,2].axhline(ssr['value'].mean()*100, color='red', linestyle='--')
            axes[0,2].set_title('SSR (%)')
            axes[0,2].set_ylim(0, 100)

        # 4. Buffer Hit Ratio
        hr = self.df[self.df['metric_type'] == 'HR_buf']
        if len(hr) > 0:
            axes[1,0].plot(hr['timestamp'], hr['value'], 's-', color='#FDCB6E')
            axes[1,0].set_title('Buffer Hit Ratio (%)')
            axes[1,0].tick_params(axis='x', rotation=45)

        # 5. Tempo de Ingestão
        ingest = self.df[self.df['metric_type'] == 'T_ingest']
        if len(ingest) > 0:
            axes[1,1].bar(range(len(ingest)), ingest['value'], color='#A29BFE', edgecolor='black')
            axes[1,1].set_title('Tempo de Ingestão (s)')

        # 6. Memória
        mem = self.df[self.df['metric_type'] == 'M_peak']
        if len(mem) > 0:
            axes[1,2].bar(range(len(mem)), mem['value'], color='#FD79A8', edgecolor='black')
            axes[1,2].set_title('Pico de Memória (MB)')

        plt.tight_layout()
        output_path = self.output_dir / 'dashboard_metrics.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"📊 Dashboard salvo: {output_path}")

    # ============================================================
    # EXPORTAÇÃO PARA TABELAS DO TCC
    # ============================================================
    def export_tables(self):
        """Exporta tabelas formatadas para inserção no TCC."""
        summary = self.summary()

        # Tabela 1: Resumo estatístico
        table_data = []
        for mtype, stats in summary.items():
            table_data.append({
                'Métrica': mtype,
                'Unidade': stats['unit'],
                'N': stats['count'],
                'Mín': stats['min'],
                'Máx': stats['max'],
                'Média': stats['mean'],
                'Mediana': stats['median'],
                'Desv.Padrão': stats['std']
            })

        df_table = pd.DataFrame(table_data)

        # Salva como CSV
        csv_path = self.output_dir / 'tabela_resumo_metricas.csv'
        df_table.to_csv(csv_path, index=False, encoding='utf-8')

        # Salva como Markdown
        md_path = self.output_dir / 'tabela_resumo_metricas.md'
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(df_table.to_markdown(index=False))

        print(f"📋 Tabelas exportadas:")
        print(f"   CSV: {csv_path}")
        print(f"   MD:  {md_path}")

        return df_table

    def run_all(self):
        """Executa análise completa."""
        self.load()
        self.print_summary()
        self.plot_baseline()
        self.plot_latency_timeline()
        self.plot_throughput()
        self.plot_ssr()
        self.plot_buffer_ratio()
        self.plot_memory()
        self.plot_dashboard()
        self.export_tables()

        print(f"✅ Análise completa! Resultados em: {self.output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Análise e visualização de métricas do CodeHelper"
    )
    parser.add_argument("--input", "-i", required=True, 
                       help="Arquivo JSONL de métricas (ex: ./metrics/metrics_20260607_120000.jsonl)")
    parser.add_argument("--output", "-o", default="./tcc_graficos",
                       help="Diretório de saída para gráficos")
    args = parser.parse_args()

    analyzer = MetricsAnalyzer(args.input, args.output)
    analyzer.run_all()


if __name__ == "__main__":
    main()
