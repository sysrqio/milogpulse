#!/usr/bin/env python3
"""CLI entrypoint for milogpulse."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from milogpulse import __version__
from milogpulse.audit import audit_timesheet, format_markdown, format_text


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="milogpulse",
        description="MiLoG / FKS timesheet pre-audit",
    )
    p.add_argument("--version", action="version", version=f"milogpulse {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Audit a timesheet CSV export")
    audit.add_argument("--export", required=True, help="Path to CSV export")
    audit.add_argument(
        "--profile",
        choices=("generic", "takt", "personio"),
        default="generic",
        help="Column profile",
    )
    audit.add_argument(
        "--late-days",
        type=int,
        default=7,
        help="MiLoG recording deadline in days after work day",
    )
    audit.add_argument(
        "--output",
        choices=("text", "json", "markdown"),
        default="text",
        help="Report format",
    )
    audit.add_argument("--out-file", help="Write report to file")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit":
        export = Path(args.export)
        if not export.exists():
            print(f"error: export path not found: {export}", file=sys.stderr)
            return 1
        try:
            report = audit_timesheet(
                export,
                profile=args.profile,
                late_days=args.late_days,
                version=__version__,
            )
        except Exception as exc:  # noqa: BLE001 — CLI boundary
            print(f"error: {exc}", file=sys.stderr)
            return 1

        if args.output == "json":
            out = json.dumps(report.to_dict(), indent=2)
        elif args.output == "markdown":
            out = format_markdown(report)
        else:
            out = format_text(report)

        if args.out_file:
            Path(args.out_file).write_text(out, encoding="utf-8")
        else:
            print(out)
        return 0 if report.ok else 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
