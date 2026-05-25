"""Utilities for Agent F end-to-end test execution."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Mapping, Optional

ToolRunner = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]

DEFAULT_BOARD = "esp32dev"
DEFAULT_ENVIRONMENT = "esp32dev"
DEFAULT_MONITOR_BAUD = 115200


@dataclass
class LiveRunnerContext:
    """Metadata about the live runner selected for smoke tests."""

    runner: ToolRunner
    source: str
    supports_flash_monitor: bool
    detail: str


class FakeAgentFRunner:
    """Deterministic fake PlatformIO-MCP runner for offline e2e tests."""

    def __init__(
        self,
        *,
        monitor_log: str,
        board: str = DEFAULT_BOARD,
        environment: str = DEFAULT_ENVIRONMENT,
    ) -> None:
        self.board = board
        self.environment = environment
        self.monitor_log = monitor_log
        self.calls: List[str] = []

    def __call__(self, endpoint: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(endpoint)
        environment = _coalesce_text(
            params.get("environment"),
            params.get("env"),
            self.environment,
        )

        if endpoint == "agent_f.inspect":
            return {
                "status": "success",
                "board": self.board,
                "environment": environment,
                "framework": "arduino",
                "upload_port": params.get("upload_port", "COM5"),
                "monitor_speed": params.get("baud", DEFAULT_MONITOR_BAUD),
                "findings": [],
                "message": "Inspect mission complete.",
            }

        if endpoint == "agent_f.build":
            return {
                "status": "success",
                "board": self.board,
                "environment": environment,
                "findings": [],
                "message": "Build mission complete.",
            }

        if endpoint == "agent_f.flash":
            return {
                "status": "success",
                "board": self.board,
                "environment": environment,
                "findings": [],
                "message": "Flash mission complete.",
            }

        if endpoint == "agent_f.monitor":
            return {
                "status": "success",
                "board": self.board,
                "environment": environment,
                "logs": self.monitor_log,
                "findings": [],
                "message": "Monitor mission complete.",
            }

        if endpoint == "agent_f.diagnose":
            combined_text = "\n".join(
                [self.monitor_log, _extract_context_text(params)]
            ).strip()
            findings = classify_common_issues(combined_text)
            status = "partial" if findings else "success"
            return {
                "status": status,
                "board": self.board,
                "environment": environment,
                "findings": findings,
                "fixes": [],
                "message": "Diagnosis mission complete.",
            }

        if endpoint == "agent_f.repair":
            return {
                "status": "partial",
                "board": self.board,
                "environment": environment,
                "findings": classify_common_issues(self.monitor_log),
                "fixes": [
                    {"summary": "Reassigned unsafe GPIO and added startup delay."}
                ],
                "message": "Repair suggestions generated.",
            }

        return {
            "status": "failed",
            "board": self.board,
            "environment": environment,
            "findings": [{"issue": f"unknown endpoint: {endpoint}", "severity": "high"}],
            "message": f"Unsupported endpoint: {endpoint}",
        }


class PioCliSmokeRunner:
    """Reduced live smoke runner backed by PlatformIO CLI."""

    def __init__(self, *, project_dir: Path, pio_cmd: str) -> None:
        self.project_dir = project_dir
        self.pio_cmd = pio_cmd

    def __call__(self, endpoint: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        environment = _coalesce_text(
            params.get("environment"),
            params.get("env"),
            DEFAULT_ENVIRONMENT,
        )
        board = _coalesce_text(params.get("board"), DEFAULT_BOARD)

        if endpoint == "agent_f.inspect":
            return _inspect_project(self.project_dir, environment)

        if endpoint == "agent_f.build":
            return _build_project_with_pio(
                project_dir=self.project_dir,
                pio_cmd=self.pio_cmd,
                environment=environment,
                board=board,
            )

        if endpoint == "agent_f.diagnose":
            findings = classify_common_issues(_extract_context_text(params))
            status = "partial" if findings else "success"
            return {
                "status": status,
                "tool": "pio-cli-diagnose",
                "board": board,
                "environment": environment,
                "findings": findings,
                "message": "Diagnosis generated from live smoke context.",
            }

        return {
            "status": "failed",
            "tool": "pio-cli-smoke",
            "board": board,
            "environment": environment,
            "findings": [
                {
                    "issue": (
                        f"CLI smoke fallback does not support endpoint '{endpoint}'."
                    ),
                    "severity": "info",
                }
            ],
            "message": "Endpoint unsupported in CLI smoke fallback.",
        }


def resolve_live_runner(project_dir: Path) -> LiveRunnerContext:
    """Resolve the optional live test runner.

    Priority:
    1. Adapter from `AGENT_F_E2E_TOOL_RUNNER` (`module:function`).
    2. PlatformIO CLI fallback (`pio`) for reduced smoke coverage.
    """

    spec = os.getenv("AGENT_F_E2E_TOOL_RUNNER", "").strip()
    upload_port = os.getenv("AGENT_F_E2E_UPLOAD_PORT", "").strip()
    monitor_baud = os.getenv("AGENT_F_E2E_MONITOR_BAUD", "").strip()
    has_hardware_vars = bool(upload_port and monitor_baud)

    if spec:
        runner = _load_adapter_callable(spec)
        detail = f"Loaded adapter runner from {spec}."
        if not has_hardware_vars:
            detail = (
                f"{detail} Flash/monitor smoke disabled until both "
                "AGENT_F_E2E_UPLOAD_PORT and AGENT_F_E2E_MONITOR_BAUD are set."
            )
        return LiveRunnerContext(
            runner=runner,
            source="adapter",
            supports_flash_monitor=has_hardware_vars,
            detail=detail,
        )

    pio_cmd = shutil.which("pio")
    if pio_cmd:
        return LiveRunnerContext(
            runner=PioCliSmokeRunner(project_dir=project_dir, pio_cmd=pio_cmd),
            source="pio-cli",
            supports_flash_monitor=False,
            detail=(
                "Using pio CLI fallback. Reduced smoke covers inspect/build/diagnose; "
                "flash/monitor tests are skipped."
            ),
        )

    raise RuntimeError(
        "Live mode enabled, but no runner is available. "
        "Set AGENT_F_E2E_TOOL_RUNNER=module:function or install pio."
    )


def load_fixture_text(path: Path) -> str:
    """Read fixture text as UTF-8 with replacement for resilience."""

    return path.read_text(encoding="utf-8", errors="replace")


def classify_common_issues(text: str) -> List[Dict[str, Any]]:
    """Classify log text into Agent F issue buckets."""

    lowered = text.lower()
    findings: List[Dict[str, Any]] = []

    if any(token in lowered for token in ("gpio0", "gpio 0", "gpio12", "boot mode")):
        findings.append(
            {"issue": "strapping pin misuse", "severity": "warn", "evidence": ["boot mode"]}
        )
    if "brownout" in lowered or "rst:0x" in lowered:
        findings.append(
            {"issue": "brownout symptoms", "severity": "high", "evidence": ["brownout"]}
        )
    if "watchdog" in lowered or "wdt" in lowered:
        findings.append(
            {
                "issue": "blocking setup()/loop() logic",
                "severity": "warn",
                "evidence": ["watchdog"],
            }
        )
    if "upload_port" in lowered or "could not open port" in lowered:
        findings.append(
            {"issue": "missing upload_port", "severity": "warn", "evidence": ["upload_port"]}
        )
    if "wrong target" in lowered or "unknown board" in lowered:
        findings.append(
            {"issue": "wrong board target", "severity": "high", "evidence": ["wrong target"]}
        )

    deduped: Dict[str, Dict[str, Any]] = {}
    for finding in findings:
        deduped[str(finding["issue"])] = finding
    return list(deduped.values())


def _load_adapter_callable(spec: str) -> ToolRunner:
    if ":" not in spec:
        raise ValueError(
            "AGENT_F_E2E_TOOL_RUNNER must be 'module:function', "
            f"got '{spec}'."
        )
    module_name, attr_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    candidate = getattr(module, attr_name, None)
    if not callable(candidate):
        raise TypeError(
            "AGENT_F_E2E_TOOL_RUNNER must reference a callable with signature "
            "(endpoint, params) -> mapping."
        )
    return candidate


def _inspect_project(project_dir: Path, environment: str) -> Mapping[str, Any]:
    ini_path = project_dir / "platformio.ini"
    if not ini_path.exists():
        return {
            "status": "failed",
            "tool": "pio-cli-inspect",
            "board": "unknown",
            "environment": environment,
            "findings": [{"issue": "platformio.ini not found", "severity": "high"}],
            "message": f"Missing file: {ini_path}",
        }

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str.lower
    parser.read(ini_path, encoding="utf-8")
    section = f"env:{environment}"
    board = parser.get(section, "board", fallback=DEFAULT_BOARD)
    framework = parser.get(section, "framework", fallback="")
    upload_port = parser.get(section, "upload_port", fallback="")
    monitor_speed = parser.get(section, "monitor_speed", fallback="")

    findings = []
    if not upload_port:
        findings.append({"issue": "missing upload_port", "severity": "warn"})
    if not monitor_speed:
        findings.append(
            {"issue": "missing monitor_speed (baud may be ambiguous)", "severity": "warn"}
        )

    return {
        "status": "success",
        "tool": "pio-cli-inspect",
        "board": board,
        "environment": environment,
        "framework": framework,
        "upload_port": upload_port,
        "monitor_speed": monitor_speed,
        "findings": findings,
        "message": f"Inspected environment '{environment}' via pio CLI fallback.",
    }


def _build_project_with_pio(
    *,
    project_dir: Path,
    pio_cmd: str,
    environment: str,
    board: str,
) -> Mapping[str, Any]:
    command = [pio_cmd, "--no-ansi", "run", "-e", environment]
    try:
        result = subprocess.run(
            command,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + "\n" + (exc.stderr or "")
        return {
            "status": "failed",
            "tool": "pio-cli-build",
            "board": board,
            "environment": environment,
            "findings": [{"issue": "pio build timeout", "severity": "high"}],
            "output": output[-4000:],
            "message": "pio build timed out.",
        }

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    status = "success" if result.returncode == 0 else "failed"
    findings = []
    if status == "failed":
        findings.append({"issue": "pio build failed", "severity": "high"})
    return {
        "status": status,
        "tool": "pio-cli-build",
        "board": board,
        "environment": environment,
        "findings": findings,
        "output": output[-4000:],
        "message": f"pio build exited with code {result.returncode}.",
    }


def _extract_context_text(params: Mapping[str, Any]) -> str:
    chunks: List[str] = []
    context = params.get("context")
    _collect_text(context, chunks)
    logs = params.get("logs")
    _collect_text(logs, chunks)
    return "\n".join(chunks)


def _collect_text(value: Any, chunks: List[str]) -> None:
    if isinstance(value, str):
        chunks.append(value)
        return
    if isinstance(value, Mapping):
        for nested in value.values():
            _collect_text(nested, chunks)
        return
    if isinstance(value, list):
        for item in value:
            _collect_text(item, chunks)


def _coalesce_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
