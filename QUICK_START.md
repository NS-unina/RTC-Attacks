# Quick Start Guide - Experimental Validation

## Overview

Questa guida ti aiuta a eseguire rapidamente gli esperimenti per rispondere ai commenti dei revisori.

## Prerequisites

### Software Richiesti
```bash
# Sistema base (già installati)
- Docker & Docker Compose
- Python 3.8+
- bash/zsh
- make

# Python packages aggiuntivi
pip install pandas numpy matplotlib seaborn scipy

# Tools di analisi
sudo apt-get install tshark  # Per analisi PCAP
```

### File Necessari
```bash
pip install -r scripts/requirements.txt
```

## Quick Start - Esecuzione Completa

### Opzione 1: Test Rapido (5 run, 1 scenario)
```bash
# Test su un singolo scenario per verificare funzionamento
chmod +x scripts/run_experiments.sh
./scripts/run_experiments.sh 5 4_rtp_bleed_injection_asterisk

# Analisi risultati
python3 scripts/statistical_analysis.py experimental_results/run_<timestamp>
```

### Opzione 2: Esperimento Completo (30 run, tutti gli scenari)
```bash
# ATTENZIONE: Questo richiede diverse ore!
./scripts/run_experiments.sh 30

# Analisi risultati
python3 scripts/statistical_analysis.py experimental_results/run_<timestamp>
```

### Opzione 3: Manuale Step-by-Step

#### Step 1: Raccolta Metriche per Singolo Scenario
```bash
# Esempio per scenario RTP Bleed
cd public/labs/4_rtp_bleed_injection_asterisk

# Cleanup
make stop clean

# Start con timing
time make start

# Monitoring risorse in background
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" > metrics.txt &
STATS_PID=$!

# Esegui attacco
make auto-attack

# Stop monitoring
kill $STATS_PID

# Raccogli catture
ls -lh ../../captures/

# Cleanup
make stop
cd ../../..
```

#### Step 2: Analisi Metriche Raccolte
```python
# Usando la libreria metrics_collector
from scripts.metrics_collector import MetricsCollector

collector = MetricsCollector(output_dir="my_metrics")

# Analizza PCAP più recente
latest_pcap = "captures/latest/capture.pcap"
latency_metrics = collector.collect_network_latency(latest_pcap)
print(latency_metrics)

# Calcola detection metrics (se hai ground truth)
ids_metrics = collector.collect_ids_metrics("ground_truth.csv", "captures/latest/alert.log")
print(f"Precision: {ids_metrics['precision']:.3f}")
print(f"Recall: {ids_metrics['recall']:.3f}")
print(f"F1: {ids_metrics['f1_score']:.3f}")
```

## Struttura Output

Dopo aver eseguito `run_experiments.sh`, troverai:

```
experimental_results/run_<timestamp>/
├── config.json                    # Configurazione esperimento
├── REPORT.md                      # Report riassuntivo
├── metrics/                       # Metriche grezze
│   ├── <scenario>_run1_timing.json
│   ├── <scenario>_run1_resources.csv
│   ├── <scenario>_run1_detection.json
│   └── ...
├── logs/                          # Log esecuzione
│   ├── <scenario>_run1_build.log
│   ├── <scenario>_run1_attack.log
│   └── ...
├── captures/                      # PCAP e alert
│   ├── <scenario>_run1/
│   │   ├── capture.pcap
│   │   └── alert.log
│   └── ...
├── analysis/                      # Analisi statistiche
│   ├── STATISTICAL_SUMMARY.md
│   ├── timing_table.tex          # Tabella LaTeX per paper
│   └── <scenario>_summary.json
└── plots/                         # Grafici publication-ready
    ├── timing_boxplot.png
    ├── resource_timeseries_<scenario>.png
    └── detection_rate.png
```

## Metriche Raccolte

### 1. Performance Metrics (Comment 4)

#### Deployment Timing
- **Build time**: Tempo costruzione immagini Docker
- **Startup time**: Tempo avvio container
- **Ready time**: Tempo fino a servizio disponibile
- **Total time**: Tempo totale deployment

File: `metrics/<scenario>_runN_timing.json`

#### Resource Usage
- **CPU**: Utilizzo percentuale per container
- **Memory**: Utilizzo memoria (MB) per container
- **Network I/O**: Byte RX/TX

File: `metrics/<scenario>_runN_resources.csv`

#### Network Latency
- **SIP RTT**: Round-trip time per transazioni SIP
- **RTP Jitter**: Variazione timing pacchetti RTP
- **Packet Loss**: Percentuale pacchetti persi

Calcolo: `collector.collect_network_latency(pcap_file)`

### 2. IDS Detection Metrics (Comment 3)

#### Detection Accuracy
- **Precision**: TP / (TP + FP)
- **Recall**: TP / (TP + FN)
- **F1-Score**: Media armonica Precision/Recall
- **Accuracy**: (TP + TN) / Total

File: `metrics/<scenario>_runN_detection.json`

#### Packet Capture Completeness
- **Capture Rate**: % pacchetti catturati vs inviati
- **Packet Loss**: % pacchetti persi

Calcolo: `collector.collect_capture_completeness()`

#### Correlation Metrics
- **Correlation Rate**: % alert correlati a eventi reali
- **Time to Detection**: Tempo tra attacco e primo alert

### 3. Statistical Validation (Comments 1, 2)

#### Reproducibility
- **Success Rate**: % run completati con successo
- **Coefficient of Variation (CV)**: Variabilità metriche
- **Confidence Intervals**: 95% CI per ogni metrica

Output: `analysis/STATISTICAL_SUMMARY.md`

#### Comparative Analysis
- **ANOVA/Kruskal-Wallis**: Confronto tra scenari
- **t-tests**: Confronto paired con/senza monitoring
- **Effect sizes**: Cohen's d per differenze

## Interpretazione Risultati

### Cosa Aspettarsi

#### Deployment Timing (Target)
- Build time: 20-60 secondi (dipende da complessità scenario)
- Startup time: 5-15 secondi
- Ready time: 3-10 secondi
- **Total**: 30-85 secondi

#### Resource Usage (Target)
- CPU baseline: 5-10% per container
- CPU durante attacco: 15-40% per container attaccato
- Memory: 100-500 MB per container (dipende da applicazione)

#### Network Latency (Target)
- SIP RTT overhead: < 5ms con monitoring
- RTP Jitter: < 10ms
- Packet Loss: < 1%

#### IDS Detection (Target)
- **Precision**: > 90% (pochi falsi positivi)
- **Recall**: > 95% (pochi falsi negativi)
- **F1**: > 0.93
- Capture rate: > 99%
- Time to detection: < 500ms

### Red Flags

🚨 **Problemi da Investigare**:
- CV > 15%: Troppa variabilità, ambiente non stabile
- Success rate < 95%: Problemi di affidabilità
- Detection recall < 90%: IDS non rileva abbastanza
- Packet loss > 5%: Problemi cattura traffico
- Memory trending crescente: Possibile memory leak

## Generazione Report per Revisori

### Tabelle per Manoscritto

Le tabelle LaTeX sono generate automaticamente:
```bash
# File generato:
analysis/timing_table.tex
```

Esempio output:
```latex
\begin{table}[htbp]
\centering
\caption{Deployment Timing Metrics (seconds)}
\label{tab:deployment_timing}
\begin{tabular}{lcccc}
\toprule
Scenario & build_time & startup_time & ready_time & total_time \\
\midrule
4_rtp_bleed & $32.4 \pm 2.1$ & $8.2 \pm 0.5$ & $5.1 \pm 0.3$ & $45.7 \pm 2.4$ \\
...
\bottomrule
\end{tabular}
\end{table}
```

### Grafici per Manoscritto

Tutti i grafici sono salvati in alta risoluzione (300 DPI):
- `plots/timing_boxplot.png`: Box plot tempi deployment
- `plots/resource_timeseries_<scenario>.png`: Serie temporali CPU/Memory
- `plots/detection_rate.png`: Detection rate con CI

### Testo per Risposta ai Revisori

Usa il template in `EXPERIMENTAL_DESIGN.md` sezione 6 "Expected Outcomes" come base per le risposte.

Esempio per **Comment 4**:
```
We have conducted extensive performance analysis including:
- Deployment time: mean 45.2±2.4s per scenario (breakdown: build 32.4±2.1s, 
  startup 8.2±0.5s, ready 5.1±0.3s, N=30, 95% CI: 42.8-47.6s)
- Resource utilization: CPU 18.3±3.2% during attack execution, 
  Memory 387±45 MB per scenario
- Network overhead: 2.3±0.5ms latency increase (statistically significant, 
  p<0.001, paired t-test), negligible impact on VoIP QoS
- IDS detection rate: Precision 94.2%, Recall 97.5%, F1-score 0.95
- Reproducibility: 97.3% success rate over 30 runs per scenario, 
  CV < 8% for all timing metrics
```

## Advanced Usage

### Custom Metrics Collection

Estendi `metrics_collector.py` per metriche specifiche:

```python
class MyCustomCollector(MetricsCollector):
    def collect_voip_quality(self, pcap_file: str) -> Dict:
        """Calcola MOS score per VoIP quality"""
        # Implementa calcolo personalizzato
        pass
```

### Long-Running Stability Test

```bash
# Test di stabilità 24h (vedi EXPERIMENTAL_DESIGN.md sezione 3.3)
# ATTENZIONE: Richiede 24 ore!

# Modifica script per long run
vim scripts/run_experiments.sh  # Modifica duration in collect_resource_metrics

# Esegui con monitoring prolungato
./scripts/run_experiments.sh 1 4_rtp_bleed_injection_asterisk

# Analizza trend temporali per memory leaks
python3 scripts/statistical_analysis.py experimental_results/run_<timestamp>
```

### Scalability Tests

```bash
# Test con numero variabile di client (vedi EXPERIMENTAL_DESIGN.md sezione 3.2)

# TODO: Implementare script scalability_test.sh
# Per ora, manualmente:

for num_clients in 1 5 10 20 50; do
    echo "Testing with $num_clients clients..."
    # Modifica docker-compose per scalare client
    # Esegui esperimento
    # Raccogli metriche
done
```

## Troubleshooting

### Problema: Docker containers non si avviano
```bash
# Cleanup completo
docker-compose down -v
docker system prune -af
docker volume prune -f

# Riprova build
make build
```

### Problema: Metriche non raccolte
```bash
# Verifica permessi
ls -la experimental_results/
chmod -R u+w experimental_results/

# Verifica docker stats funziona
docker stats --no-stream
```

### Problema: Tshark non disponibile
```bash
# Installa Wireshark/tshark
sudo apt-get update
sudo apt-get install tshark

# Configura permessi per non-root
sudo usermod -aG wireshark $USER
# Logout/login per applicare
```

### Problema: Python dependencies mancanti
```bash
pip install -r scripts/requirements.txt

# O manualmente
pip install pandas numpy matplotlib seaborn scipy
```

## Roadmap Implementazione

### Fase 1: Validazione Framework (1 giorno)
- [ ] Esegui test rapido (5 run, 1 scenario)
- [ ] Verifica generazione metriche
- [ ] Verifica analisi statistica
- [ ] Fix eventuali problemi

### Fase 2: Completare Metriche Mancanti (1 settimana)
- [ ] Implementare `_calculate_sip_rtt()` in metrics_collector.py
- [ ] Implementare `_calculate_rtp_jitter()` 
- [ ] Implementare `_parse_snort_alerts()`
- [ ] Implementare ground truth generation per ogni scenario
- [ ] Testare capture completeness

### Fase 3: Esperimenti Completi (1 settimana)
- [ ] Eseguire 30 run per ogni scenario (~210 run totali)
- [ ] Analisi statistica completa
- [ ] Generazione grafici publication-ready
- [ ] Scrittura sezione Results aggiornata

### Fase 4: Esperimenti Avanzati (2 settimane - opzionale)
- [ ] Scalability tests
- [ ] Configuration comparison (Snort tuning)
- [ ] Long-running stability tests
- [ ] Latency overhead measurement (con/senza monitoring)

## Risorse Addizionali

- **Design completo**: `EXPERIMENTAL_DESIGN.md`
- **Metrics collector**: `scripts/metrics_collector.py`
- **Test runner**: `scripts/run_experiments.sh`
- **Statistical analysis**: `scripts/statistical_analysis.py`

## Support

Per problemi o domande:
1. Controlla troubleshooting sopra
2. Verifica logs in `experimental_results/run_<timestamp>/logs/`
3. Controlla issues su repository

## Esempio Workflow Completo

```bash
# 1. Setup
cd /path/to/RTC-Attacks
pip install -r scripts/requirements.txt
chmod +x scripts/run_experiments.sh

# 2. Test rapido (5 minuti)
./scripts/run_experiments.sh 5 4_rtp_bleed_injection_asterisk

# 3. Analisi
python3 scripts/statistical_analysis.py experimental_results/run_<timestamp>

# 4. Verifica output
ls experimental_results/run_<timestamp>/plots/
cat experimental_results/run_<timestamp>/analysis/STATISTICAL_SUMMARY.md

# 5. Se tutto OK, esegui esperimento completo (diverse ore)
./scripts/run_experiments.sh 30

# 6. Analisi finale
python3 scripts/statistical_analysis.py experimental_results/run_<timestamp>

# 7. Integra risultati nel paper
# - Copia tabelle LaTeX da analysis/
# - Copia grafici PNG da plots/
# - Usa template risposte in EXPERIMENTAL_DESIGN.md sezione 6
```

**Buona fortuna con gli esperimenti! 🚀**
