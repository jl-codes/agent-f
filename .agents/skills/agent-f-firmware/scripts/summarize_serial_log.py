#!/usr/bin/env python3
"""Summarize PlatformIO serial output and classify common failure patterns."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Pattern


RULES: Dict[str, List[Pattern[str]]] = {
    "strapping pin misuse": [
        re.compile(r"\bgpio\s*0\b", re.IGNORECASE),
        re.compile(r"\bgpio\s*2\b", re.IGNORECASE),
        re.compile(r"\bgpio\s*12\b", re.IGNORECASE),
        re.compile(r"boot mode", re.IGNORECASE),
    ],
    "wrong baud rate": [
        re.compile(r"garbled|\?\?\?|\x00", re.IGNORECASE),
        re.compile(r"baud", re.IGNORECASE),
    ],
    "wrong board target": [
        re.compile(r"invalid header", re.IGNORECASE),
        re.compile(r"incompatible", re.IGNORECASE),
        re.compile(r"wrong chip|wrong target", re.IGNORECASE),
    ],
    "missing upload_port": [
        re.compile(r"could not open port", re.IGNORECASE),
        re.compile(r"no such file or directory.*tty|com", re.IGNORECASE),
    ],
    "unsafe gpio selection": [
        re.compile(r"input-only", re.IGNORECASE),
        re.compile(r"pin .* invalid", re.IGNORECASE),
    ],
    "brownout symptoms": [
        re.compile(r"brownout", re.IGNORECASE),
        re.compile(r"rst:\s*0x", re.IGNORECASE),
    ],
    "blocking setup()/loop() logic": [
        re.compile(r"watchdog|wdt", re.IGNORECASE),
        re.compile(r"task watchdog got triggered", re.IGNORECASE),
    ],
}


def read_log(path: str) -> str:
    if path == "-":
        import sys

        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def classify(text: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for issue, patterns in RULES.items():
        evidence: List[str] = []
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                evidence.append(match.group(0))
        if evidence:
            severity = "warn"
            if issue in {"brownout symptoms", "wrong board target"}:
                severity = "high"
            findings.append(
                {
                    "issue": issue,
                    "severity": severity,
                    "evidence": evidence[:3],
                }
            )
    return findings


def summarize(text: str) -> Dict[str, Any]:
    lines = [line for line in text.splitlines() if line.strip()]
    findings = classify(text)
    status = "success" if not findings else "partial"
    if any(item["severity"] == "high" for item in findings):
        status = "failed"

    return {
        "status": status,
        "tool": "summarize_serial_log.py",
        "board": "unknown",
        "line_count": len(lines),
        "findings": findings,
        "agent_f_message": (
            f"Processed {len(lines)} log lines and identified {len(findings)} finding(s)."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "log_path",
        help="Path to serial log file, or '-' to read from stdin.",
    )
    args = parser.parse_args()

    text = read_log(args.log_path)
    report = summarize(text)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
