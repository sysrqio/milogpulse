"""MiLoG-oriented timesheet CSV audit (local, no network)."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from dateutil import parser as date_parser

CSV_DELIM = ";"


@dataclass
class Violation:
    code: str
    message: str
    severity: str = "error"


@dataclass
class AuditReport:
    tool: str = "milogpulse"
    version: str = "0.1.0"
    scanned_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    export_path: str = ""
    profile: str = "generic"
    rows_checked: int = 0
    policy_violations: List[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.policy_violations) == 0

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "version": self.version,
            "scanned_at": self.scanned_at,
            "export_path": self.export_path,
            "profile": self.profile,
            "rows_checked": self.rows_checked,
            "policy_violations": [
                {"code": v.code, "message": v.message, "severity": v.severity}
                for v in self.policy_violations
            ],
        }


PROFILE_COLUMNS: Dict[str, Dict[str, str]] = {
    "generic": {
        "work_date": "work_date",
        "start": "start",
        "end": "end",
        "recorded_at": "recorded_at",
        "employee": "employee",
    },
    "takt": {
        "work_date": "Datum",
        "start": "Beginn",
        "end": "Ende",
        "recorded_at": "Erfasst_am",
        "employee": "Mitarbeiter",
    },
    "personio": {
        "work_date": "date",
        "start": "start_time",
        "end": "end_time",
        "recorded_at": "created_at",
        "employee": "employee_id",
    },
}


def _normalize_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _resolve_columns(headers: Sequence[str], profile: str) -> Dict[str, Optional[str]]:
    mapping = PROFILE_COLUMNS.get(profile, PROFILE_COLUMNS["generic"])
    norm = {_normalize_header(h): h for h in headers}
    resolved: Dict[str, Optional[str]] = {}
    for key, expected in mapping.items():
        exp_norm = _normalize_header(expected)
        resolved[key] = norm.get(exp_norm)
        if not resolved[key]:
            for h in headers:
                if exp_norm in _normalize_header(h):
                    resolved[key] = h
                    break
    return resolved


def _parse_date(value: str) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if iso:
        y, m, d = map(int, iso.groups())
        return date(y, m, d)
    try:
        return date_parser.parse(value, dayfirst=True).date()
    except (ValueError, TypeError):
        return None


def _parse_datetime(value: str) -> Optional[datetime]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date_parser.parse(value, dayfirst=True)
    except (ValueError, TypeError):
        return None


def _read_csv(path: Path) -> Tuple[List[str], List[dict]]:
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        # Sniff delimiter
        sample = fh.read(2048)
        fh.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(fh, delimiter=delim)
        headers = reader.fieldnames or []
        rows = [dict(r) for r in reader]
    return list(headers), rows


def _check_batch_entry(recorded_times: List[datetime], threshold: int = 5) -> List[Violation]:
    if len(recorded_times) < threshold:
        return []
    # Same minute bucket for many rows
    buckets: Dict[str, int] = {}
    for dt in recorded_times:
        key = dt.replace(second=0, microsecond=0).isoformat()
        buckets[key] = buckets.get(key, 0) + 1
    for key, count in buckets.items():
        if count >= threshold:
            return [
                Violation(
                    code="BATCH_ENTRY_SUSPECT",
                    message=(
                        f"{count} rows share recorded_at bucket {key} — "
                        "possible month-end batch entry"
                    ),
                )
            ]
    return []


def audit_timesheet(
    export_path: Path,
    profile: str = "generic",
    late_days: int = 7,
    version: str = "0.1.0",
) -> AuditReport:
    report = AuditReport(
        version=version,
        export_path=str(export_path),
        profile=profile,
    )
    if not export_path.is_file():
        raise FileNotFoundError(f"Export not found: {export_path}")

    headers, rows = _read_csv(export_path)
    if not rows:
        report.policy_violations.append(
            Violation(code="EMPTY_EXPORT", message="CSV has no data rows")
        )
        return report

    cols = _resolve_columns(headers, profile)
    for required in ("work_date", "start", "end"):
        if not cols.get(required):
            report.policy_violations.append(
                Violation(
                    code="MISSING_COLUMN",
                    message=f"Profile {profile}: column for {required} not found",
                )
            )
            return report

    recorded_times: List[datetime] = []
    report.rows_checked = len(rows)

    for i, row in enumerate(rows, start=2):
        wd = _parse_date(row.get(cols["work_date"] or "", ""))
        start = (row.get(cols["start"] or "", "") or "").strip()
        end = (row.get(cols["end"] or "", "") or "").strip()

        if not start:
            report.policy_violations.append(
                Violation(
                    code="MISSING_START",
                    message=f"Row {i}: missing start time",
                )
            )
        if not end:
            report.policy_violations.append(
                Violation(
                    code="MISSING_END",
                    message=f"Row {i}: missing end time",
                )
            )
        if start and end and start == end:
            report.policy_violations.append(
                Violation(
                    code="INVALID_DURATION",
                    message=f"Row {i}: start equals end",
                )
            )

        rec_col = cols.get("recorded_at")
        if rec_col and row.get(rec_col):
            rec_dt = _parse_datetime(row[rec_col])
            if rec_dt and wd:
                recorded_times.append(rec_dt)
                deadline = wd + timedelta(days=late_days)
                if rec_dt.date() > deadline:
                    report.policy_violations.append(
                        Violation(
                            code="LATE_RECORDING",
                            message=(
                                f"Row {i}: recorded {rec_dt.date()} > "
                                f"{late_days} days after work day {wd}"
                            ),
                        )
                    )

    report.policy_violations.extend(_check_batch_entry(recorded_times))
    return report


def format_text(report: AuditReport) -> str:
    lines = [
        f"MiLoGPulse audit v{report.version}",
        f"Export: {report.export_path} (profile={report.profile})",
        f"Rows checked: {report.rows_checked}",
    ]
    if report.ok:
        lines.append("Result: OK — no policy violations")
    else:
        lines.append(f"Result: FAIL — {len(report.policy_violations)} violation(s)")
        for v in report.policy_violations:
            lines.append(f"  - [{v.code}] {v.message}")
    return "\n".join(lines)


def format_markdown(report: AuditReport) -> str:
    body = format_text(report)
    return f"# MiLoGPulse audit report\n\n```\n{body}\n```\n"
