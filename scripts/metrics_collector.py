#!/usr/bin/env python3
"""
Metrics Collector for RTC-Attacks Testbed
Raccoglie metriche di performance, risorse e detection per validazione scientifica
"""

import subprocess
import json
import time
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import statistics

class MetricsCollector:
    def __init__(self, output_dir: str = "metrics"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.current_run = {}
        
    def collect_deployment_timing(self, scenario_name: str) -> Dict:
        """
        Misura timing di deployment per uno scenario
        Ritorna: {build_time, startup_time, ready_time, total_time}
        """
        metrics = {
            'scenario': scenario_name,
            'timestamp': datetime.now().isoformat()
        }
        
        # Build time
        print(f"[*] Measuring build time for {scenario_name}...")
        start = time.time()
        result = subprocess.run(
            ['make', 'build'],
            cwd=f'public/labs/{scenario_name}',
            capture_output=True
        )
        metrics['build_time'] = time.time() - start
        metrics['build_success'] = result.returncode == 0
        
        # Startup time
        print(f"[*] Measuring startup time...")
        start = time.time()
        subprocess.run(['make', 'start'], cwd=f'public/labs/{scenario_name}')
        metrics['startup_time'] = time.time() - start
        
        # Ready time (wait for SIP registration)
        print(f"[*] Waiting for services ready...")
        start = time.time()
        ready = self._wait_for_ready(scenario_name)
        metrics['ready_time'] = time.time() - start
        metrics['ready_success'] = ready
        
        metrics['total_time'] = metrics['build_time'] + metrics['startup_time'] + metrics['ready_time']
        
        return metrics
    
    def collect_resource_usage(self, duration_seconds: int = 60, sample_interval: float = 0.1) -> List[Dict]:
        """
        Raccoglie CPU e memoria per tutti i container in esecuzione
        
        Args:
            duration_seconds: Durata del monitoring
            sample_interval: Intervallo tra campioni (secondi)
        
        Returns:
            Lista di snapshot delle metriche
        """
        print(f"[*] Collecting resource metrics for {duration_seconds}s...")
        metrics = []
        
        end_time = time.time() + duration_seconds
        
        while time.time() < end_time:
            timestamp = time.time()
            
            # Docker stats (formato JSON)
            result = subprocess.run(
                ['docker', 'stats', '--no-stream', '--format', 
                 '{"container":"{{.Container}}","cpu":"{{.CPUPerc}}","memory":"{{.MemUsage}}","net_io":"{{.NetIO}}"}'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        try:
                            data = json.loads(line)
                            data['timestamp'] = timestamp
                            
                            # Parse percentuali e valori
                            data['cpu_percent'] = float(data['cpu'].rstrip('%'))
                            
                            # Parse memoria (formato "XXMiB / YYMiB")
                            mem_parts = data['memory'].split('/')
                            data['memory_used_mb'] = self._parse_memory(mem_parts[0])
                            data['memory_limit_mb'] = self._parse_memory(mem_parts[1]) if len(mem_parts) > 1 else 0
                            
                            metrics.append(data)
                        except (json.JSONDecodeError, ValueError) as e:
                            print(f"[!] Error parsing stats: {e}")
            
            time.sleep(sample_interval)
        
        return metrics
    
    def collect_network_latency(self, pcap_file: str) -> Dict:
        """
        Calcola latency metrics da file PCAP usando tshark
        
        Returns:
            {sip_rtt_avg, sip_rtt_std, rtp_jitter_avg, packet_loss_rate}
        """
        print(f"[*] Analyzing network latency from {pcap_file}...")
        
        metrics = {}
        
        # Analisi SIP RTT (INVITE -> 200 OK)
        sip_rtts = self._calculate_sip_rtt(pcap_file)
        if sip_rtts:
            metrics['sip_rtt_avg_ms'] = statistics.mean(sip_rtts)
            metrics['sip_rtt_std_ms'] = statistics.stdev(sip_rtts) if len(sip_rtts) > 1 else 0
            metrics['sip_rtt_min_ms'] = min(sip_rtts)
            metrics['sip_rtt_max_ms'] = max(sip_rtts)
            metrics['sip_rtt_median_ms'] = statistics.median(sip_rtts)
        
        # Analisi RTP jitter
        jitter_values = self._calculate_rtp_jitter(pcap_file)
        if jitter_values:
            metrics['rtp_jitter_avg_ms'] = statistics.mean(jitter_values)
            metrics['rtp_jitter_std_ms'] = statistics.stdev(jitter_values) if len(jitter_values) > 1 else 0
        
        # Packet loss
        metrics['packet_loss_rate'] = self._calculate_packet_loss(pcap_file)
        
        return metrics
    
    def collect_ids_metrics(self, ground_truth_file: str, alert_file: str) -> Dict:
        """
        Calcola metriche IDS: precision, recall, F1, accuracy
        
        Args:
            ground_truth_file: CSV con ground truth (timestamp, src_ip, dst_ip, is_malicious)
            alert_file: File alert di Snort
        
        Returns:
            {precision, recall, f1, accuracy, tp, fp, tn, fn}
        """
        print(f"[*] Calculating IDS detection metrics...")
        
        # Parse ground truth
        ground_truth = self._parse_ground_truth(ground_truth_file)
        
        # Parse Snort alerts
        alerts = self._parse_snort_alerts(alert_file)
        
        # Matching e calcolo confusion matrix
        tp = fp = tn = fn = 0
        
        for packet in ground_truth:
            alert_found = self._find_matching_alert(packet, alerts, max_time_delta=1.0)
            
            if packet['is_malicious'] and alert_found:
                tp += 1
            elif packet['is_malicious'] and not alert_found:
                fn += 1
            elif not packet['is_malicious'] and alert_found:
                fp += 1
            else:
                tn += 1
        
        # Calcolo metriche
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0
        
        return {
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'accuracy': accuracy,
            'true_positives': tp,
            'false_positives': fp,
            'true_negatives': tn,
            'false_negatives': fn,
            'total_alerts': len(alerts),
            'total_malicious': sum(1 for p in ground_truth if p['is_malicious'])
        }
    
    def collect_capture_completeness(self, sent_pcap: str, captured_pcap: str, filter_ip: str) -> Dict:
        """
        Verifica completezza capture confrontando pacchetti inviati vs catturati
        
        Returns:
            {packets_sent, packets_captured, capture_rate, packet_loss}
        """
        print(f"[*] Checking packet capture completeness...")
        
        # Conta pacchetti inviati
        result = subprocess.run(
            ['tshark', '-r', sent_pcap, '-Y', f'ip.src == {filter_ip}', '-T', 'fields', '-e', 'frame.number'],
            capture_output=True,
            text=True
        )
        packets_sent = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
        
        # Conta pacchetti catturati
        result = subprocess.run(
            ['tshark', '-r', captured_pcap, '-Y', f'ip.src == {filter_ip}', '-T', 'fields', '-e', 'frame.number'],
            capture_output=True,
            text=True
        )
        packets_captured = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
        
        capture_rate = (packets_captured / packets_sent * 100) if packets_sent > 0 else 0
        packet_loss = 100 - capture_rate
        
        return {
            'packets_sent': packets_sent,
            'packets_captured': packets_captured,
            'capture_rate_percent': capture_rate,
            'packet_loss_percent': packet_loss
        }
    
    def save_metrics(self, metrics: Dict, filename: str):
        """Salva metriche in JSON"""
        output_file = self.output_dir / filename
        with open(output_file, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"[+] Metrics saved to {output_file}")
    
    def save_metrics_csv(self, metrics_list: List[Dict], filename: str):
        """Salva lista di metriche in CSV"""
        if not metrics_list:
            return
        
        output_file = self.output_dir / filename
        keys = metrics_list[0].keys()
        
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(metrics_list)
        
        print(f"[+] Metrics saved to {output_file}")
    
    # Helper methods
    
    def _wait_for_ready(self, scenario_name: str, timeout: int = 120) -> bool:
        """Aspetta che il servizio sia pronto (es. SIP registrato)"""
        # TODO: Implementare check specifico per scenario
        # Placeholder: sleep fisso
        time.sleep(5)
        return True
    
    def _parse_memory(self, mem_str: str) -> float:
        """Converte string memoria (es. '234MiB') in MB"""
        mem_str = mem_str.strip()
        if 'GiB' in mem_str:
            return float(mem_str.replace('GiB', '')) * 1024
        elif 'MiB' in mem_str:
            return float(mem_str.replace('MiB', ''))
        elif 'KiB' in mem_str:
            return float(mem_str.replace('KiB', '')) / 1024
        else:
            return 0.0
    
    def _calculate_sip_rtt(self, pcap_file: str) -> List[float]:
        """Calcola RTT per transazioni SIP INVITE->200 OK"""
        # TODO: Implementare parsing con tshark/scapy
        # Placeholder
        return []
    
    def _calculate_rtp_jitter(self, pcap_file: str) -> List[float]:
        """Calcola jitter RTP secondo RFC 3550"""
        # TODO: Implementare calcolo jitter
        # Placeholder
        return []
    
    def _calculate_packet_loss(self, pcap_file: str) -> float:
        """Calcola packet loss rate da sequence numbers RTP"""
        # TODO: Implementare analisi sequence numbers
        # Placeholder
        return 0.0
    
    def _parse_ground_truth(self, filename: str) -> List[Dict]:
        """Parse CSV ground truth"""
        ground_truth = []
        with open(filename) as f:
            reader = csv.DictReader(f)
            for row in reader:
                row['is_malicious'] = row['is_malicious'].lower() in ['true', '1', 'yes']
                ground_truth.append(row)
        return ground_truth
    
    def _parse_snort_alerts(self, alert_file: str) -> List[Dict]:
        """Parse file alert di Snort"""
        alerts = []
        # TODO: Implementare parsing formato Snort (fast alert o unified2)
        # Placeholder
        return alerts
    
    def _find_matching_alert(self, packet: Dict, alerts: List[Dict], max_time_delta: float = 1.0) -> bool:
        """Trova alert corrispondente a un pacchetto (matching temporale + IP)"""
        # TODO: Implementare matching con time window
        # Placeholder
        return False


def main():
    """Esempio di utilizzo"""
    collector = MetricsCollector(output_dir="metrics")
    print("[*] Collecting deployment timing...")
    
    # Test deployment timing
    # metrics = collector.collect_deployment_timing("4_rtp_bleed_injection_asterisk")
    # collector.save_metrics(metrics, "deployment_timing.json")
    
    # Test resource monitoring
    # resource_metrics = collector.collect_resource_usage(duration_seconds=10)
    # collector.save_metrics_csv(resource_metrics, "resource_usage.csv")
    
    print("[+] Metrics collector ready. Use as library or extend for your scenarios.")


if __name__ == "__main__":
    main()
