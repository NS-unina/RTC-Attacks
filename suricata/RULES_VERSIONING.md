# Suricata Rules Versioning

This directory contains multiple versions of the RTC-Attacks detection ruleset to track the evolution and fine-tuning process.

## File Structure

### `local.rules.v1-baseline`
**Baseline ruleset** - Original rules converted from Snort, BEFORE any fine-tuning activities.

**Purpose**: Methodological comparison for research papers to demonstrate the impact of rule tuning.

**Known Issues**:
- **SID 2000003** (SIP overflow): Generates false positives on legitimate SIP REGISTER messages
  - Root cause: PCRE pattern `/tag=.{80,}/smi` with `/s` flag makes dot match newlines
  - Impact: Counts 80+ characters across multiple lines (including Authorization headers)
  - False positive rate: 3 FP per legitimate SIP client registration in test scenario 1

**Test Results** (Scenario 1 isolated):
```
Total alerts: 4
├─ 1x SID 2000001 ✅ (True Positive: SIP spoofing attack)
└─ 3x SID 2000003 ❌ (False Positives: legitimate sip-cli-1001 REGISTER)
```

### `local.rules`
**Current working ruleset** - Active version with ongoing fine-tuning improvements.

**Changelog**:
- **SID 2000003 rev:3** - Fixed false positives
  - Changed PCRE: `/tag=.{80,}/smi` → `/tag=[^\r\n]{80,}/mi`
  - Impact: Removed `/s` flag, now matches 80+ chars on same line only
  - Result: 0 false positives on scenario 1 test

- **SID 2000002 rev:3** - Optimized alert volume for REGISTER flood
  - Changed threshold: `type threshold, count 150, seconds 5` → `type limit, count 150, seconds 30`
  - Impact: Reduced alert storm from 19,300 alerts to ~1 alert per attack
  - Result: Preserved detection, improved SIEM usability

**Test Results** (Scenario 1 isolated):
```
Total alerts: 1
└─ 1x SID 2000001 ✅ (True Positive: SIP spoofing attack)
```

### `local.rules.vN-production` (future)
**Production-ready ruleset** - Final version after complete fine-tuning and validation.

This file will be created after:
1. Testing all 9 scenarios individually
2. Running parallel scenario validation
3. Analyzing and fixing any remaining false positives/negatives
4. Final validation with `make exp1-baseline`

## Fine-Tuning Methodology

### Phase 1: Baseline Testing ✅
1. Created baseline rules from Snort conversion
2. Tested scenario 1 (SIP spoofing) in isolation
3. Identified false positive in SID 2000003

### Phase 2: Iterative Tuning 🔄
1. Analyze false positives using PCAP inspection
2. Modify PCRE/content patterns to reduce FP while preserving TP
3. Validate fix with isolated scenario test
4. Document change with rev increment and changelog

### Phase 3: Full Validation (TODO)
1. Test all scenarios individually with `make cleanup-all` between runs
2. Run parallel scenario validation
3. Compare detection rates: baseline vs tuned
4. Document precision/recall improvements

## Usage for Research Papers

### Comparing Baseline vs Tuned

```bash
# Test with baseline rules
cp suricata/local.rules.v1-baseline suricata/local.rules
make cleanup-all && make start-suricata
# ... run scenario tests ...

# Test with tuned rules  
git restore suricata/local.rules
make cleanup-all && make start-suricata
# ... run scenario tests ...
```

### Metrics to Report

- **False Positive Reduction**: Count of FP alerts (baseline vs tuned)
- **True Positive Preservation**: Ensure attack detection remains 100%
- **Rule Complexity**: Number of content matches, PCRE patterns
- **Performance Impact**: Detection latency, CPU usage (if measured)

### Example Paper Section

```
We conducted an iterative fine-tuning process on our IDS ruleset:

Initial baseline (v1): 10 rules covering 9 attack scenarios
├─ Scenario 1 test: 1 TP + 3 FP (75% false positive rate)
└─ Issue: SID 2000003 PCRE /s flag caused multi-line matching

After tuning (v2): Modified SID 2000003 to same-line matching only
├─ Scenario 1 test: 1 TP + 0 FP (0% false positive rate)  
└─ Fix: PCRE /tag=[^\r\n]{80,}/mi eliminates newline matches

False positive reduction: 100% (3→0 FP for scenario 1)
True positive preservation: 100% (attack still detected)
```

## Version Control

All rule versions are tracked in git for reproducibility:
- Commit baseline before any changes
- Document each tuning iteration in commit messages
- Tag major milestones (e.g., `rules-v1-baseline`, `rules-v2-production`)

## See Also

- `../docs/EXPERIMENTS.md` - Experiment workflow and methodology
- `../experiments/pipeline/ids_dataset_pipeline.py` - Alert generation and validation
