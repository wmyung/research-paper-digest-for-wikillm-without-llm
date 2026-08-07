import json
import subprocess
import sys
from pathlib import Path


def test_no_llm_audit_passes():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(root / "scripts/no-llm-audit.py"), str(root)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(completed.stdout)
    assert report["success"] is True
    assert report["model_runtime_dependencies"] == 0
    assert report["external_inference_calls"] == 0
    assert report["paper_text_external_transmission"] == 0
