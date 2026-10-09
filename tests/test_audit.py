import subprocess
import sys
from pathlib import Path

from milogpulse.audit import audit_timesheet

ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "testdata" / "valid_timesheet.csv"
LATE = ROOT / "testdata" / "late_recording.csv"
BATCH = ROOT / "testdata" / "batch_suspect.csv"


def test_valid_export_ok():
    report = audit_timesheet(VALID)
    assert report.ok
    assert report.rows_checked == 2


def test_late_recording():
    report = audit_timesheet(LATE)
    assert not report.ok
    assert any(v.code == "LATE_RECORDING" for v in report.policy_violations)


def test_batch_suspect_cli_exit_2():
    proc = subprocess.run(
        [sys.executable, "-m", "milogpulse", "audit", "--export", str(BATCH)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "BATCH_ENTRY_SUSPECT" in proc.stdout


def test_missing_export_returns_1():
    proc = subprocess.run(
        [sys.executable, "-m", "milogpulse", "audit", "--export", "/no/such/path"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
