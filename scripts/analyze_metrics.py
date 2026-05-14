#!/usr/bin/env python3
"""
Statistical Analysis and Visualization for Experimental Metrics

This script analyzes the CSV/JSON metrics collected by the metrics.mk framework
and generates publication-ready tables and figures for addressing reviewer comments.

Usage:
    python3 analyze_metrics.py --metrics-dir labs/1_2_sip_spoofing_dos_freeswitch/metrics
    python3 analyze_metrics.py --all-labs  # Analyze all labs
    
Output:
    - Statistical summary tables (LaTeX/Markdown)
    - Performance graphs (PDF/PNG)
    - Reproducibility analysis
    - IDS effectiveness metrics
"""

import argparse
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List
import sys

# Optional: matplotlib for visualizations
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False
    print("[!] Warning: matplotlib/seaborn not available. Plotting disabled.")
    print("[*] Install with: pip install matplotlib seaborn")


class MetricsAnalyzer:
    """Analyzes experimental metrics and generates reports"""
    
    def __init__(self, metrics_dir: Path):
        self.metrics_dir = Path(metrics_dir)
        self.results = {}
        
    def analyze_all(self):
        """Run all analysis functions"""
        print(f"[*] Analyzing metrics in: {self.metrics_dir}")
        
        self.analyze_deployment_time()
        self.analyze_resource_utilization()
        self.analyze_network_latency()
        self.analyze_reproducibility()
        self.analyze_ids_detection()
        self.analyze_pcap_completeness()
        self.analyze_correlation()
        
        return self.results
    
    def analyze_deployment_time(self):
        """Analyze build and startup times"""
        print("\n=== Deployment Time Analysis ===")
        
        build_files = list(self.metrics_dir.glob("build_time_*.csv"))
        startup_files = list(self.metrics_dir.glob("startup_time_*.csv"))
        
        if not build_files:
            print("[!] No build time data found")
            return
        
        # Combine all build time measurements
        build_data = pd.concat([pd.read_csv(f) for f in build_files])
        build_times = build_data['duration_sec'].astype(float)
        
        stats = {
            'mean': build_times.mean(),
            'std': build_times.std(),
            'min': build_times.min(),
            'max': build_times.max(),
            'median': build_times.median(),
            'cv': (build_times.std() / build_times.mean()) * 100  # Coefficient of variation
        }
        
        print(f"Build Time: {stats['mean']:.3f} ± {stats['std']:.3f} sec")
        print(f"Range: [{stats['min']:.3f}, {stats['max']:.3f}] sec")
        print(f"Coefficient of Variation: {stats['cv']:.2f}%")
        
        self.results['deployment_time'] = stats
        
    def analyze_resource_utilization(self):
        """Analyze CPU and memory usage"""
        print("\n=== Resource Utilization Analysis ===")
        
        baseline_files = list(self.metrics_dir.glob("cpu_mem_baseline_*.csv"))
        attack_files = list(self.metrics_dir.glob("cpu_mem_attack_*.csv"))
        
        if not baseline_files and not attack_files:
            print("[!] No resource utilization data found")
            return
        
        results = {}
        
        if baseline_files:
            baseline_df = pd.concat([pd.read_csv(f) for f in baseline_files])
            # Parse CPU percentage (remove % sign)
            baseline_df['cpu_pct'] = baseline_df['cpu_percent'].str.rstrip('%').astype(float)
            baseline_df['mem_pct'] = baseline_df['mem_percent'].str.rstrip('%').astype(float)
            
            results['baseline'] = {
                'cpu_mean': baseline_df['cpu_pct'].mean(),
                'cpu_std': baseline_df['cpu_pct'].std(),
                'mem_mean': baseline_df['mem_pct'].mean(),
                'mem_std': baseline_df['mem_pct'].std(),
            }
            
            print("Baseline:")
            print(f"  CPU: {results['baseline']['cpu_mean']:.2f} ± {results['baseline']['cpu_std']:.2f}%")
            print(f"  MEM: {results['baseline']['mem_mean']:.2f} ± {results['baseline']['mem_std']:.2f}%")
        
        if attack_files:
            attack_df = pd.concat([pd.read_csv(f) for f in attack_files])
            attack_df['cpu_pct'] = attack_df['cpu_percent'].str.rstrip('%').astype(float)
            attack_df['mem_pct'] = attack_df['mem_percent'].str.rstrip('%').astype(float)
            
            results['attack'] = {
                'cpu_mean': attack_df['cpu_pct'].mean(),
                'cpu_std': attack_df['cpu_pct'].std(),
                'cpu_peak': attack_df['cpu_pct'].max(),
                'mem_mean': attack_df['mem_pct'].mean(),
                'mem_std': attack_df['mem_pct'].std(),
                'mem_peak': attack_df['mem_pct'].max(),
            }
            
            print("Attack:")
            print(f"  CPU: {results['attack']['cpu_mean']:.2f} ± {results['attack']['cpu_std']:.2f}% (peak: {results['attack']['cpu_peak']:.2f}%)")
            print(f"  MEM: {results['attack']['mem_mean']:.2f} ± {results['attack']['mem_std']:.2f}% (peak: {results['attack']['mem_peak']:.2f}%)")
            
            # Calculate overhead
            if 'baseline' in results:
                cpu_overhead = ((results['attack']['cpu_mean'] - results['baseline']['cpu_mean']) / 
                              results['baseline']['cpu_mean'] * 100)
                mem_overhead = ((results['attack']['mem_mean'] - results['baseline']['mem_mean']) / 
                              results['baseline']['mem_mean'] * 100)
                
                results['overhead'] = {
                    'cpu_pct': cpu_overhead,
                    'mem_pct': mem_overhead
                }
                
                print(f"\nOverhead:")
                print(f"  CPU: +{cpu_overhead:.1f}%")
                print(f"  MEM: +{mem_overhead:.1f}%")
        
        self.results['resource_utilization'] = results
        
    def analyze_network_latency(self):
        """Analyze network latency overhead"""
        print("\n=== Network Latency Analysis ===")
        
        baseline_files = list(self.metrics_dir.glob("network_baseline_*.csv"))
        monitoring_files = list(self.metrics_dir.glob("network_monitoring_*.csv"))
        
        if not baseline_files or not monitoring_files:
            print("[!] Incomplete network latency data")
            return
        
        baseline_df = pd.concat([pd.read_csv(f) for f in baseline_files])
        monitoring_df = pd.concat([pd.read_csv(f) for f in monitoring_files])
        
        baseline_rtt = baseline_df['rtt_ms'].astype(float)
        monitoring_rtt = monitoring_df['rtt_ms'].astype(float)
        
        # Remove zeros (failed pings)
        baseline_rtt = baseline_rtt[baseline_rtt > 0]
        monitoring_rtt = monitoring_rtt[monitoring_rtt > 0]
        
        stats = {
            'baseline_mean': baseline_rtt.mean(),
            'baseline_std': baseline_rtt.std(),
            'monitoring_mean': monitoring_rtt.mean(),
            'monitoring_std': monitoring_rtt.std(),
            'overhead_ms': monitoring_rtt.mean() - baseline_rtt.mean(),
            'overhead_pct': ((monitoring_rtt.mean() - baseline_rtt.mean()) / baseline_rtt.mean() * 100)
                            if baseline_rtt.mean() > 0 else 0
        }
        
        print(f"Baseline RTT: {stats['baseline_mean']:.3f} ± {stats['baseline_std']:.3f} ms")
        print(f"With Monitoring: {stats['monitoring_mean']:.3f} ± {stats['monitoring_std']:.3f} ms")
        print(f"Overhead: {stats['overhead_ms']:.3f} ms ({stats['overhead_pct']:.2f}%)")
        
        self.results['network_latency'] = stats
        
    def analyze_reproducibility(self):
        """Analyze reproducibility statistics from N runs"""
        print("\n=== Reproducibility Analysis ===")
        
        repro_files = list(self.metrics_dir.glob("reproducibility_*.csv"))
        
        if not repro_files:
            print("[!] No reproducibility data found")
            return
        
        df = pd.concat([pd.read_csv(f) for f in repro_files])
        
        total_runs = len(df)
        
        # Success rates (exit code 0 = success)
        build_success_rate = (df['build_success'] == 0).sum() / total_runs * 100
        start_success_rate = (df['start_success'] == 0).sum() / total_runs * 100
        attack_success_rate = (df['attack_success'] == 0).sum() / total_runs * 100
        detection_success_rate = df['detection_success'].sum() / total_runs * 100
        
        # Timing statistics
        build_time_mean = df['build_time_sec'].mean()
        build_time_std = df['build_time_sec'].std()
        build_time_cv = (build_time_std / build_time_mean * 100) if build_time_mean > 0 else 0
        
        startup_time_mean = df['startup_time_sec'].mean()
        startup_time_std = df['startup_time_sec'].std()
        startup_time_cv = (startup_time_std / startup_time_mean * 100) if startup_time_mean > 0 else 0
        
        stats = {
            'total_runs': total_runs,
            'build_success_rate': build_success_rate,
            'start_success_rate': start_success_rate,
            'attack_success_rate': attack_success_rate,
            'detection_success_rate': detection_success_rate,
            'build_time': {'mean': build_time_mean, 'std': build_time_std, 'cv': build_time_cv},
            'startup_time': {'mean': startup_time_mean, 'std': startup_time_std, 'cv': startup_time_cv}
        }
        
        print(f"Total runs: {total_runs}")
        print(f"\nSuccess Rates:")
        print(f"  Build: {build_success_rate:.1f}%")
        print(f"  Start: {start_success_rate:.1f}%")
        print(f"  Attack: {attack_success_rate:.1f}%")
        print(f"  Detection: {detection_success_rate:.1f}%")
        print(f"\nTiming Variability:")
        print(f"  Build: {build_time_mean:.2f} ± {build_time_std:.2f}s (CV: {build_time_cv:.1f}%)")
        print(f"  Startup: {startup_time_mean:.2f} ± {startup_time_std:.2f}s (CV: {startup_time_cv:.1f}%)")
        
        self.results['reproducibility'] = stats
        
    def analyze_ids_detection(self):
        """Analyze IDS detection metrics"""
        print("\n=== IDS Detection Analysis ===")
        
        ids_files = list(self.metrics_dir.glob("ids_metrics_*.json"))
        
        if not ids_files:
            print("[!] No IDS metrics data found")
            return
        
        # Load latest metrics
        with open(ids_files[-1]) as f:
            metrics = json.load(f)
        
        print(f"Precision: {metrics.get('precision', 0):.3f}")
        print(f"Recall: {metrics.get('recall', 0):.3f}")
        print(f"F1-Score: {metrics.get('f1', 0):.3f}")
        print(f"Accuracy: {metrics.get('accuracy', 0):.3f}")
        print(f"\nConfusion Matrix:")
        print(f"  TP: {metrics.get('TP', 0)}, FP: {metrics.get('FP', 0)}")
        print(f"  FN: {metrics.get('FN', 0)}, TN: {metrics.get('TN', 0)}")
        
        self.results['ids_detection'] = metrics
        
    def analyze_pcap_completeness(self):
        """Analyze packet capture completeness"""
        print("\n=== Packet Capture Completeness ===")
        
        pcap_files = list(self.metrics_dir.glob("pcap_completeness_*.csv"))
        
        if not pcap_files:
            print("[!] No PCAP completeness data found")
            return
        
        df = pd.concat([pd.read_csv(f) for f in pcap_files])
        
        avg_capture_rate = df['capture_rate_pct'].mean()
        avg_packet_loss = df['packet_loss_pct'].mean()
        
        stats = {
            'capture_rate': avg_capture_rate,
            'packet_loss': avg_packet_loss,
            'total_sent': df['packets_sent'].sum(),
            'total_captured': df['packets_captured'].sum()
        }
        
        print(f"Capture Rate: {avg_capture_rate:.2f}%")
        print(f"Packet Loss: {avg_packet_loss:.2f}%")
        print(f"Total: {stats['total_captured']}/{stats['total_sent']} packets")
        
        self.results['pcap_completeness'] = stats
        
    def analyze_correlation(self):
        """Analyze alert-event correlation"""
        print("\n=== Alert-Event Correlation ===")
        
        corr_files = list(self.metrics_dir.glob("correlation_*.json"))
        
        if not corr_files:
            print("[!] No correlation data found")
            return
        
        with open(corr_files[-1]) as f:
            metrics = json.load(f)
        
        print(f"Correlation Rate: {metrics.get('correlation_rate', 0):.2f}%")
        print(f"Total Events: {metrics.get('total_events', 0)}")
        print(f"Matched Events: {metrics.get('matched_events', 0)}")
        
        self.results['correlation'] = metrics
    
    def generate_latex_table(self):
        """Generate LaTeX table for paper"""
        print("\n=== LaTeX Table ===")
        
        latex = r"""
\begin{table}[htbp]
\centering
\caption{Experimental Metrics Summary}
\label{tab:metrics}
\begin{tabular}{lcc}
\toprule
\textbf{Metric} & \textbf{Value} & \textbf{Unit} \\
\midrule
"""
        
        if 'deployment_time' in self.results:
            dt = self.results['deployment_time']
            latex += f"Build Time & ${dt['mean']:.2f} \\pm {dt['std']:.2f}$ & sec \\\\\n"
        
        if 'resource_utilization' in self.results and 'attack' in self.results['resource_utilization']:
            ru = self.results['resource_utilization']['attack']
            latex += f"CPU Peak & {ru['cpu_peak']:.1f} & \\% \\\\\n"
            latex += f"Memory Peak & {ru['mem_peak']:.1f} & \\% \\\\\n"
        
        if 'network_latency' in self.results:
            nl = self.results['network_latency']
            latex += f"Latency Overhead & {nl['overhead_ms']:.2f} ({nl['overhead_pct']:.1f}\\%) & ms \\\\\n"
        
        if 'reproducibility' in self.results:
            rp = self.results['reproducibility']
            latex += f"Attack Success Rate & {rp['attack_success_rate']:.1f} & \\% \\\\\n"
            latex += f"Detection Success Rate & {rp['detection_success_rate']:.1f} & \\% \\\\\n"
        
        if 'ids_detection' in self.results:
            ids = self.results['ids_detection']
            latex += f"IDS Precision & {ids['precision']:.3f} & - \\\\\n"
            latex += f"IDS Recall & {ids['recall']:.3f} & - \\\\\n"
            latex += f"IDS F1-Score & {ids['f1']:.3f} & - \\\\\n"
        
        latex += r"""\bottomrule
\end{tabular}
\end{table}
"""
        
        print(latex)
        return latex
    
    def save_report(self, output_file: Path):
        """Save complete report to file"""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            f.write("# Experimental Metrics Analysis Report\n\n")
            f.write(f"Metrics Directory: {self.metrics_dir}\n\n")
            
            for category, data in self.results.items():
                f.write(f"## {category.replace('_', ' ').title()}\n\n")
                f.write(f"```json\n{json.dumps(data, indent=2)}\n```\n\n")
        
        print(f"\n[+] Report saved to: {output_file}")


def analyze_all_labs(labs_base_dir: Path):
    """Analyze metrics from all labs and generate comparison table"""
    print("=== Multi-Lab Analysis ===\n")
    
    all_results = {}
    
    for lab_dir in labs_base_dir.glob("*/"):
        if not lab_dir.is_dir():
            continue
        
        metrics_dir = lab_dir / "metrics"
        if not metrics_dir.exists():
            continue
        
        print(f"\n[*] Analyzing {lab_dir.name}...")
        analyzer = MetricsAnalyzer(metrics_dir)
        results = analyzer.analyze_all()
        all_results[lab_dir.name] = results
    
    # Generate comparison table
    print("\n=== Cross-Lab Comparison ===")
    comparison_df = pd.DataFrame()
    
    for lab_name, results in all_results.items():
        row = {'Lab': lab_name}
        
        if 'reproducibility' in results:
            row['Attack Success (%)'] = results['reproducibility']['attack_success_rate']
            row['Detection Success (%)'] = results['reproducibility']['detection_success_rate']
        
        if 'ids_detection' in results:
            row['Precision'] = results['ids_detection']['precision']
            row['Recall'] = results['ids_detection']['recall']
            row['F1-Score'] = results['ids_detection']['f1']
        
        comparison_df = pd.concat([comparison_df, pd.DataFrame([row])], ignore_index=True)
    
    print("\n" + comparison_df.to_string(index=False))
    print("\n" + comparison_df.to_markdown(index=False))
    
    return all_results


def main():
    parser = argparse.ArgumentParser(description="Analyze experimental metrics")
    parser.add_argument('--metrics-dir', type=Path, help='Path to metrics directory')
    parser.add_argument('--all-labs', action='store_true', help='Analyze all labs')
    parser.add_argument('--labs-dir', type=Path, 
                       default=Path('/home/gx1/git/Unina/RTC-Attacks/public/labs'),
                       help='Base directory for labs (for --all-labs)')
    parser.add_argument('--output', type=Path, help='Output report file')
    parser.add_argument('--latex', action='store_true', help='Generate LaTeX table')
    
    args = parser.parse_args()
    
    if args.all_labs:
        all_results = analyze_all_labs(args.labs_dir)
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(all_results, f, indent=2)
            print(f"\n[+] Multi-lab results saved to: {args.output}")
    
    elif args.metrics_dir:
        analyzer = MetricsAnalyzer(args.metrics_dir)
        results = analyzer.analyze_all()
        
        if args.latex:
            analyzer.generate_latex_table()
        
        if args.output:
            analyzer.save_report(args.output)
        else:
            print("\n=== Results Summary ===")
            print(json.dumps(results, indent=2))
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
