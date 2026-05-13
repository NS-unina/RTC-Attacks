#!/usr/bin/env python3
"""
Statistical Analysis for RTC-Attacks Experimental Results
Genera tabelle e grafici publication-ready con analisi statistica rigorosa
"""

import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from scipy import stats
from typing import Dict, List, Tuple
import sys

# Configurazione stile per pubblicazione
sns.set_style("whitegrid")
sns.set_context("paper", font_scale=1.5)
plt.rcParams['figure.dpi'] = 300
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['font.family'] = 'serif'

class StatisticalAnalyzer:
    def __init__(self, results_dir: str):
        self.results_dir = Path(results_dir)
        self.metrics_dir = self.results_dir / "metrics"
        self.analysis_dir = self.results_dir / "analysis"
        self.plots_dir = self.results_dir / "plots"
        
        self.plots_dir.mkdir(exist_ok=True)
        
    def load_timing_metrics(self) -> pd.DataFrame:
        """Carica tutte le metriche di timing da JSON"""
        timing_files = list(self.metrics_dir.glob("*_timing.json"))
        
        data = []
        for f in timing_files:
            with open(f) as file:
                metrics = json.load(file)
                data.append(metrics)
        
        return pd.DataFrame(data)
    
    def load_resource_metrics(self) -> pd.DataFrame:
        """Carica metriche risorse da CSV"""
        resource_files = list(self.metrics_dir.glob("*_resources.csv"))
        
        dfs = []
        for f in resource_files:
            # Estrai scenario e run dal filename
            parts = f.stem.split('_run')
            scenario = parts[0]
            run_number = int(parts[1].replace('_resources', ''))
            
            df = pd.read_csv(f)
            df['scenario'] = scenario
            df['run_number'] = run_number
            dfs.append(df)
        
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    
    def load_detection_metrics(self) -> pd.DataFrame:
        """Carica metriche detection IDS"""
        detection_files = list(self.metrics_dir.glob("*_detection.json"))
        
        data = []
        for f in detection_files:
            with open(f) as file:
                metrics = json.load(file)
                data.append(metrics)
        
        return pd.DataFrame(data)
    
    def calculate_statistics(self, df: pd.DataFrame, metric_col: str, group_by: str = 'scenario') -> pd.DataFrame:
        """
        Calcola statistiche descrittive per una metrica
        
        Returns DataFrame con: mean, std, median, min, max, ci_lower, ci_upper, cv
        """
        stats_data = []
        
        for group_name, group_df in df.groupby(group_by):
            values = group_df[metric_col].dropna()
            
            if len(values) == 0:
                continue
            
            mean_val = values.mean()
            std_val = values.std()
            median_val = values.median()
            min_val = values.min()
            max_val = values.max()
            
            # Confidence interval (95%)
            ci = stats.t.interval(0.95, len(values)-1, loc=mean_val, scale=stats.sem(values))
            
            # Coefficient of Variation
            cv = (std_val / mean_val * 100) if mean_val != 0 else 0
            
            stats_data.append({
                group_by: group_name,
                'metric': metric_col,
                'n': len(values),
                'mean': mean_val,
                'std': std_val,
                'median': median_val,
                'min': min_val,
                'max': max_val,
                'ci_lower': ci[0],
                'ci_upper': ci[1],
                'cv_percent': cv,
                'q25': values.quantile(0.25),
                'q75': values.quantile(0.75),
                'q95': values.quantile(0.95),
                'q99': values.quantile(0.99)
            })
        
        return pd.DataFrame(stats_data)
    
    def test_normality(self, df: pd.DataFrame, metric_col: str, group_by: str = 'scenario') -> pd.DataFrame:
        """Test di normalità (Shapiro-Wilk) per gruppo"""
        normality_results = []
        
        for group_name, group_df in df.groupby(group_by):
            values = group_df[metric_col].dropna()
            
            if len(values) < 3:
                continue
            
            stat, p_value = stats.shapiro(values)
            is_normal = p_value > 0.05
            
            normality_results.append({
                group_by: group_name,
                'metric': metric_col,
                'shapiro_stat': stat,
                'p_value': p_value,
                'is_normal': is_normal
            })
        
        return pd.DataFrame(normality_results)
    
    def compare_scenarios(self, df: pd.DataFrame, metric_col: str) -> Dict:
        """
        Confronto statistico tra scenari (ANOVA o Kruskal-Wallis)
        """
        groups = [group[metric_col].dropna().values for name, group in df.groupby('scenario')]
        
        # Test normalità globale
        all_normal = all(stats.shapiro(g)[1] > 0.05 for g in groups if len(g) >= 3)
        
        if all_normal and len(groups) >= 2:
            # ANOVA parametrico
            f_stat, p_value = stats.f_oneway(*groups)
            test_used = "ANOVA"
        else:
            # Kruskal-Wallis non-parametrico
            h_stat, p_value = stats.kruskal(*groups)
            f_stat = h_stat
            test_used = "Kruskal-Wallis"
        
        return {
            'test': test_used,
            'statistic': f_stat,
            'p_value': p_value,
            'significant': p_value < 0.05
        }
    
    def analyze_deployment_timing(self) -> Tuple[pd.DataFrame, Dict]:
        """Analisi completa timing deployment"""
        print("[*] Analyzing deployment timing...")
        
        df = self.load_timing_metrics()
        
        if df.empty:
            print("[!] No timing data found")
            return pd.DataFrame(), {}
        
        # Statistiche per metrica
        timing_metrics = ['build_time', 'startup_time', 'ready_time', 'total_time']
        all_stats = []
        
        for metric in timing_metrics:
            if metric in df.columns:
                stats_df = self.calculate_statistics(df, metric)
                all_stats.append(stats_df)
        
        combined_stats = pd.concat(all_stats, ignore_index=True) if all_stats else pd.DataFrame()
        
        # Test ANOVA per total_time
        comparison = self.compare_scenarios(df, 'total_time') if 'total_time' in df.columns else {}
        
        # Success rate
        success_rate = df.groupby('scenario')['build_success'].mean() * 100
        
        return combined_stats, {'comparison': comparison, 'success_rate': success_rate.to_dict()}
    
    def analyze_resource_usage(self) -> Tuple[pd.DataFrame, Dict]:
        """Analisi utilizzo risorse"""
        print("[*] Analyzing resource usage...")
        
        df = self.load_resource_metrics()
        
        if df.empty:
            print("[!] No resource data found")
            return pd.DataFrame(), {}
        
        # Aggregazione per scenario e container
        stats_by_scenario = []
        
        for scenario in df['scenario'].unique():
            scenario_df = df[df['scenario'] == scenario]
            
            for container in scenario_df['container'].unique():
                container_df = scenario_df[scenario_df['container'] == container]
                
                stats_by_scenario.append({
                    'scenario': scenario,
                    'container': container,
                    'cpu_mean': container_df['cpu_percent'].mean(),
                    'cpu_std': container_df['cpu_percent'].std(),
                    'cpu_max': container_df['cpu_percent'].max(),
                    'memory_mean': container_df['memory_used_mb'].mean(),
                    'memory_std': container_df['memory_used_mb'].std(),
                    'memory_max': container_df['memory_used_mb'].max(),
                })
        
        stats_df = pd.DataFrame(stats_by_scenario)
        
        return stats_df, {}
    
    def analyze_detection_performance(self) -> Tuple[pd.DataFrame, Dict]:
        """Analisi performance detection IDS"""
        print("[*] Analyzing IDS detection performance...")
        
        df = self.load_detection_metrics()
        
        if df.empty:
            print("[!] No detection data found")
            return pd.DataFrame(), {}
        
        # Detection rate per scenario
        detection_stats = df.groupby('scenario').agg({
            'detected': ['mean', 'std', 'sum'],
            'alerts_count': ['mean', 'std', 'max']
        }).reset_index()
        
        detection_stats.columns = ['_'.join(col).strip('_') for col in detection_stats.columns.values]
        
        # Calcolo confidence interval per detection rate
        for idx, row in detection_stats.iterrows():
            scenario = row['scenario']
            scenario_df = df[df['scenario'] == scenario]
            
            n_detected = scenario_df['detected'].sum()
            n_total = len(scenario_df)
            
            # Wilson score interval per proporzioni
            ci = self._wilson_score_interval(n_detected, n_total)
            detection_stats.loc[idx, 'detection_rate_ci_lower'] = ci[0] * 100
            detection_stats.loc[idx, 'detection_rate_ci_upper'] = ci[1] * 100
        
        detection_stats['detection_detected_mean'] *= 100  # Convert to percentage
        
        return detection_stats, {}
    
    def _wilson_score_interval(self, successes: int, total: int, confidence: float = 0.95) -> Tuple[float, float]:
        """Wilson score interval for binomial proportion"""
        if total == 0:
            return (0.0, 0.0)
        
        z = stats.norm.ppf(1 - (1 - confidence) / 2)
        p = successes / total
        
        denominator = 1 + z**2 / total
        centre = (p + z**2 / (2 * total)) / denominator
        adjustment = z * np.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denominator
        
        return (max(0, centre - adjustment), min(1, centre + adjustment))
    
    def generate_timing_table(self, stats_df: pd.DataFrame) -> str:
        """Genera tabella LaTeX per timing metrics"""
        print("[*] Generating timing table...")
        
        # Pivot per avere metriche come colonne
        pivot = stats_df.pivot(index='scenario', columns='metric', values=['mean', 'std', 'ci_lower', 'ci_upper'])
        
        # Format per pubblicazione
        latex = "\\begin{table}[htbp]\n\\centering\n"
        latex += "\\caption{Deployment Timing Metrics (seconds)}\n"
        latex += "\\label{tab:deployment_timing}\n"
        latex += "\\begin{tabular}{l" + "c" * len(stats_df['metric'].unique()) + "}\n"
        latex += "\\toprule\n"
        latex += "Scenario & " + " & ".join(stats_df['metric'].unique()) + " \\\\\n"
        latex += "\\midrule\n"
        
        for scenario in pivot.index:
            row = f"{scenario}"
            for metric in stats_df['metric'].unique():
                if metric in pivot.columns.get_level_values(1):
                    mean = pivot.loc[scenario, ('mean', metric)]
                    std = pivot.loc[scenario, ('std', metric)]
                    ci_lower = pivot.loc[scenario, ('ci_lower', metric)]
                    ci_upper = pivot.loc[scenario, ('ci_upper', metric)]
                    
                    row += f" & ${mean:.1f} \\pm {std:.1f}$"
                    # row += f"\n({ci_lower:.1f}-{ci_upper:.1f})"
            row += " \\\\\n"
            latex += row
        
        latex += "\\bottomrule\n\\end{tabular}\n\\end{table}"
        
        # Save
        output_file = self.analysis_dir / "timing_table.tex"
        with open(output_file, 'w') as f:
            f.write(latex)
        
        print(f"[+] LaTeX table saved to {output_file}")
        
        return latex
    
    def plot_timing_boxplot(self, df: pd.DataFrame):
        """Box plot timing metrics"""
        print("[*] Generating timing box plots...")
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        axes = axes.flatten()
        
        metrics = ['build_time', 'startup_time', 'ready_time', 'total_time']
        titles = ['Build Time', 'Startup Time', 'Ready Time', 'Total Deployment Time']
        
        for idx, (metric, title) in enumerate(zip(metrics, titles)):
            if metric in df.columns:
                sns.boxplot(data=df, x='scenario', y=metric, ax=axes[idx])
                axes[idx].set_title(title)
                axes[idx].set_xlabel('Scenario')
                axes[idx].set_ylabel('Time (seconds)')
                axes[idx].tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        output_file = self.plots_dir / "timing_boxplot.png"
        plt.savefig(output_file, bbox_inches='tight')
        plt.close()
        
        print(f"[+] Box plot saved to {output_file}")
    
    def plot_resource_timeseries(self, df: pd.DataFrame):
        """Time series CPU/Memory usage"""
        print("[*] Generating resource usage time series...")
        
        for scenario in df['scenario'].unique():
            scenario_df = df[df['scenario'] == scenario]
            
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
            
            # CPU plot
            for container in scenario_df['container'].unique():
                container_df = scenario_df[scenario_df['container'] == container]
                ax1.plot(container_df['timestamp'], container_df['cpu_percent'], label=container, alpha=0.7)
            
            ax1.set_ylabel('CPU Usage (%)')
            ax1.set_title(f'{scenario} - Resource Usage Over Time')
            ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
            ax1.grid(True, alpha=0.3)
            
            # Memory plot
            for container in scenario_df['container'].unique():
                container_df = scenario_df[scenario_df['container'] == container]
                ax2.plot(container_df['timestamp'], container_df['memory_used_mb'], label=container, alpha=0.7)
            
            ax2.set_xlabel('Time (seconds)')
            ax2.set_ylabel('Memory Usage (MB)')
            ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            output_file = self.plots_dir / f"resource_timeseries_{scenario}.png"
            plt.savefig(output_file, bbox_inches='tight')
            plt.close()
            
            print(f"[+] Time series plot saved to {output_file}")
    
    def plot_detection_rate(self, stats_df: pd.DataFrame):
        """Bar plot detection rate con confidence intervals"""
        print("[*] Generating detection rate plot...")
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        scenarios = stats_df['scenario']
        detection_rates = stats_df['detection_detected_mean']
        ci_lower = stats_df['detection_rate_ci_lower']
        ci_upper = stats_df['detection_rate_ci_upper']
        
        # Calcola errori per errorbar
        yerr_lower = detection_rates - ci_lower
        yerr_upper = ci_upper - detection_rates
        
        x_pos = np.arange(len(scenarios))
        bars = ax.bar(x_pos, detection_rates, yerr=[yerr_lower, yerr_upper], 
                      capsize=5, alpha=0.7, color='steelblue')
        
        ax.set_xlabel('Scenario')
        ax.set_ylabel('Detection Rate (%)')
        ax.set_title('IDS Detection Rate with 95% Confidence Intervals')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(scenarios, rotation=45, ha='right')
        ax.set_ylim([0, 105])
        ax.axhline(y=100, color='r', linestyle='--', alpha=0.3, label='Perfect Detection')
        ax.grid(True, alpha=0.3, axis='y')
        ax.legend()
        
        plt.tight_layout()
        output_file = self.plots_dir / "detection_rate.png"
        plt.savefig(output_file, bbox_inches='tight')
        plt.close()
        
        print(f"[+] Detection rate plot saved to {output_file}")
    
    def generate_summary_report(self):
        """Genera report markdown riassuntivo"""
        print("[*] Generating summary report...")
        
        report = "# Statistical Analysis Summary\n\n"
        report += f"**Analysis Date**: {pd.Timestamp.now()}\n\n"
        
        # Timing analysis
        timing_stats, timing_meta = self.analyze_deployment_timing()
        if not timing_stats.empty:
            report += "## Deployment Timing\n\n"
            report += timing_stats.to_markdown(index=False)
            report += "\n\n"
            
            if 'comparison' in timing_meta and timing_meta['comparison']:
                comp = timing_meta['comparison']
                report += f"**Statistical Comparison** ({comp['test']}): "
                report += f"F={comp['statistic']:.2f}, p={comp['p_value']:.4f}"
                if comp['significant']:
                    report += " (significant difference detected)\n\n"
                else:
                    report += " (no significant difference)\n\n"
        
        # Resource analysis
        resource_stats, _ = self.analyze_resource_usage()
        if not resource_stats.empty:
            report += "## Resource Usage\n\n"
            report += resource_stats.to_markdown(index=False)
            report += "\n\n"
        
        # Detection analysis
        detection_stats, _ = self.analyze_detection_performance()
        if not detection_stats.empty:
            report += "## IDS Detection Performance\n\n"
            report += detection_stats.to_markdown(index=False)
            report += "\n\n"
        
        # Save report
        output_file = self.analysis_dir / "STATISTICAL_SUMMARY.md"
        with open(output_file, 'w') as f:
            f.write(report)
        
        print(f"[+] Summary report saved to {output_file}")
        print("\n" + "="*60)
        print(report)
        print("="*60)
    
    def run_full_analysis(self):
        """Esegue analisi completa e genera tutti gli output"""
        print("="*60)
        print("Starting Full Statistical Analysis")
        print("="*60)
        
        # Load and analyze timing
        timing_df = self.load_timing_metrics()
        if not timing_df.empty:
            timing_stats, _ = self.analyze_deployment_timing()
            self.generate_timing_table(timing_stats)
            self.plot_timing_boxplot(timing_df)
        
        # Load and analyze resources
        resource_df = self.load_resource_metrics()
        if not resource_df.empty:
            self.analyze_resource_usage()
            self.plot_resource_timeseries(resource_df)
        
        # Load and analyze detection
        detection_df = self.load_detection_metrics()
        if not detection_df.empty:
            detection_stats, _ = self.analyze_detection_performance()
            self.plot_detection_rate(detection_stats)
        
        # Generate final summary
        self.generate_summary_report()
        
        print("\n" + "="*60)
        print("Statistical Analysis Completed!")
        print(f"Results available in: {self.results_dir}")
        print("="*60)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 statistical_analysis.py <results_directory>")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    
    if not Path(results_dir).exists():
        print(f"Error: Directory {results_dir} does not exist")
        sys.exit(1)
    
    analyzer = StatisticalAnalyzer(results_dir)
    analyzer.run_full_analysis()


if __name__ == "__main__":
    main()
