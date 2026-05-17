#!/usr/bin/env python3
"""Quick test to verify refactored experiments CLI."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

def test_cli(script_path: Path, test_name: str) -> bool:
    """Test that a CLI script shows help without errors."""
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and "Usage:" in result.stdout:
            print(f"✓ {test_name}")
            return True
        else:
            print(f"✗ {test_name}: exit code {result.returncode}")
            return False
    except Exception as exc:
        print(f"✗ {test_name}: {exc}")
        return False


def main() -> None:
    """Test all refactored CLI scripts."""
    tests = [
        (EXPERIMENTS_DIR / "exp1_baseline" / "runner.py", "exp1_baseline"),
        (EXPERIMENTS_DIR / "exp2_scalability" / "runner.py", "exp2_scalability"),
        (EXPERIMENTS_DIR / "exp3_robustness" / "runner.py", "exp3_robustness"),
        (EXPERIMENTS_DIR / "pipeline" / "ids_dataset_pipeline.py", "pipeline"),
        (EXPERIMENTS_DIR / "checks" / "collection_check.py", "collection_check"),
        (EXPERIMENTS_DIR / "checks" / "parallel_capture.py", "parallel_capture"),
    ]

    print("Testing refactored CLI scripts...\n")
    results = [test_cli(path, name) for path, name in tests]
    
    print(f"\n{sum(results)}/{len(results)} tests passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
