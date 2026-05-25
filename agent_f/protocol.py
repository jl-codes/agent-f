"""Mission protocol helpers for Agent F PlatformIO-MCP workflows.

This module exposes a small orchestration layer around the Agent F mission
endpoints:

- ``agent_f.inspect``
- ``agent_f.build``
- ``agent_f.flash``
- ``agent_f.monitor``
- ``agent_f.diagnose``
- ``agent_f.repair``

Use :func:`configure_protocol` to register a tool runner that can call
PlatformIO-MCP endpoints, then call the module-level mission helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional
import re

ToolRunner = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
CodeRepairer = Callable[[Mapping[str, Any]], Mapping[str, Any]]

_PATTERN_RULES = {
    "strapping pin misuse": [
        re.compile(r"\bgpio\s*0\b", re.IGNORECASE),
        re.compile(r"\bgpio\s*2\b", re.IGNORECASE),
        re.compile(r"\bgpio\s*12\b", re.IGNORECASE),
        re.compile(r"boot mode.*\(", re.IGNORECASE),
    ],
    "wrong baud rate": [
        re.compile(r"garbled|mojibake|\?\?\?", re.IGNORECASE),
        re.compile(r"monitor.*baud", re.IGNORECASE),
    ],
    "wrong board target": [
        re.compile(r"unknown board", re.IGNORECASE),
        re.compile(r"incompatible.*chip", re.IGNORECASE),
        re.compile(r"wrong target", re.IGNORECASE),
    ],
    "missing upload_port": [
        re.compile(r"upload_port", re.IGNORECASE),
        re.compile(r"could not open port", re.IGNORECASE),
        re.compile(r"serial port.*not found", re.IGNORECASE),
    ],
    "unsafe gpio selection": [
        re.compile(r"input-only", re.IGNORECASE),
        re.compile(r"invalid pin", re.IGNORECASE),
        re.compile(r"rtc-only", re.IGNORECASE),
    ],
    "brownout symptoms": [
        re.compile(r"brownout", re.IGNORECASE),
        re.compile(r"rst:\s*0x", re.IGNORECASE),
        re.compile(r"power.*drop", re.IGNORECASE),
    ],
    "blocking setup()/loop() logic": [
        re.compile(r"wdt", re.IGNORECASE),
        re.compile(r"watchdog", re.IGNORECASE),
        re.compile(r"task watchdog got triggered", re.IGNORECASE),
        re.compile(r"setup\(\).*hang", re.IGNORECASE),
    ],
}


@dataclass
class AgentFMissionProtocol:
    """Coordinate Agent F mission endpoint calls through PlatformIO-MCP.

    Parameters:
        tool_runner:
            Callable used to invoke PlatformIO-MCP tools. It must accept an
            endpoint name and a params mapping, then return a mapping result.
        code_repairer:
            Optional callable used by :meth:`repair` for project-local code
            adjustments after diagnosis.
    """

    tool_runner: ToolRunner
    code_repairer: Optional[CodeRepairer] = None

    def inspect(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        """Inspect board and environment configuration via ``agent_f.inspect``.

        The call validates project configuration context before build/flash and
        returns a structured mission object.
        """

        raw = self._call_tool("agent_f.inspect", params)
        board = _pick_board(raw, params)
        environment = _pick_environment(raw, params)
        findings = _as_findings(raw.get("findings"))
        return _make_result(
            status=_normalize_status(raw.get("status"), default="success"),
            tool="agent_f.inspect",
            board=board,
            environment=environment,
            findings=findings,
            agent_f_message=raw.get(
                "message",
                f"Inspection complete for board '{board or 'unknown'}' in "
                f"env '{environment or 'unknown'}'.",
            ),
            data=dict(raw),
        )

    def build(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        """Build firmware via ``agent_f.build`` and return build diagnostics.

        Use this after :meth:`inspect` to confirm the selected environment,
        compiler output, and memory usage warnings.
        """

        raw = self._call_tool("agent_f.build", params)
        board = _pick_board(raw, params)
        environment = _pick_environment(raw, params)
        findings = _as_findings(raw.get("findings"))
        return _make_result(
            status=_normalize_status(raw.get("status"), default="success"),
            tool="agent_f.build",
            board=board,
            environment=environment,
            findings=findings,
            agent_f_message=raw.get("message", "Build mission executed."),
            data=dict(raw),
        )

    def flash(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        """Flash firmware via ``agent_f.flash`` and return flashing status.

        Provide an explicit mission plan before calling this endpoint. Include
        selected board, environment, and upload port in the params.
        """

        raw = self._call_tool("agent_f.flash", params)
        board = _pick_board(raw, params)
        environment = _pick_environment(raw, params)
        findings = _as_findings(raw.get("findings"))
        return _make_result(
            status=_normalize_status(raw.get("status"), default="success"),
            tool="agent_f.flash",
            board=board,
            environment=environment,
            findings=findings,
            agent_f_message=raw.get("message", "Flash mission executed."),
            data=dict(raw),
        )

    def monitor(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        """Capture serial telemetry via ``agent_f.monitor``.

        The method returns serial logs and any first-pass findings reported by
        PlatformIO-MCP. Feed this output into :meth:`diagnose`.
        """

        raw = self._call_tool("agent_f.monitor", params)
        board = _pick_board(raw, params)
        environment = _pick_environment(raw, params)
        findings = _as_findings(raw.get("findings"))
        logs = _extract_log_text(raw)
        if logs:
            findings.extend(_classify_findings_from_text(logs))
        return _make_result(
            status=_normalize_status(raw.get("status"), default="success"),
            tool="agent_f.monitor",
            board=board,
            environment=environment,
            findings=_dedupe_findings(findings),
            agent_f_message=raw.get("message", "Monitor mission executed."),
            data=dict(raw),
        )

    def diagnose(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        """Diagnose firmware issues via ``agent_f.diagnose`` and summarize risk.

        This method combines tool-provided diagnosis with rule-based log
        interpretation and emits a concise Mission Report payload.
        """

        raw = self._call_tool("agent_f.diagnose", params)
        board = _pick_board(raw, params)
        environment = _pick_environment(raw, params)
        findings = _as_findings(raw.get("findings"))
        findings.extend(_classify_findings_from_text(_extract_any_text(params)))
        findings.extend(_classify_findings_from_text(_extract_log_text(raw)))
        findings = _dedupe_findings(findings)

        status = _normalize_status(raw.get("status"), default="partial")
        mission_report = _render_mission_report(
            board=board,
            environment=environment,
            actions=["inspect", "build", "flash", "monitor", "diagnose"],
            status=status,
            findings=findings,
            fixes=raw.get("fixes", []),
        )

        return _make_result(
            status=status,
            tool="agent_f.diagnose",
            board=board,
            environment=environment,
            findings=findings,
            agent_f_message=raw.get("message", "Diagnosis mission executed."),
            mission_report=mission_report,
            data=dict(raw),
        )

    def repair(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        """Repair firmware workflow via ``agent_f.repair`` with optional fixes.

        Steps:
        1. Call ``agent_f.repair`` for suggested remediation.
        2. Optionally apply local code changes through ``code_repairer``.
        3. Rebuild and reflash to validate the repair.

        Returns a structured result with status, findings, and a final Mission
        Report.
        """

        raw = self._call_tool("agent_f.repair", params)
        board = _pick_board(raw, params)
        environment = _pick_environment(raw, params)
        findings = _as_findings(raw.get("findings"))
        fixes_applied: List[Mapping[str, Any]] = []

        allow_code_changes = bool(params.get("allow_code_changes"))
        if allow_code_changes and self.code_repairer is not None:
            repair_result = self.code_repairer(raw)
            if repair_result:
                fixes_applied.append(dict(repair_result))

        build_result = self.build(params)
        flash_result = self.flash(params)

        statuses = {raw.get("status"), build_result["status"], flash_result["status"]}
        if "failed" in statuses:
            status = "failed"
        elif "partial" in statuses:
            status = "partial"
        else:
            status = "success"

        mission_report = _render_mission_report(
            board=board,
            environment=environment,
            actions=["repair", "build", "flash"],
            status=status,
            findings=findings,
            fixes=[*raw.get("fixes", []), *fixes_applied],
        )

        return _make_result(
            status=status,
            tool="agent_f.repair",
            board=board,
            environment=environment,
            findings=findings,
            agent_f_message=raw.get("message", "Repair mission executed."),
            mission_report=mission_report,
            data={
                "repair": dict(raw),
                "build": build_result,
                "flash": flash_result,
                "fixes_applied": fixes_applied,
            },
        )

    def _call_tool(self, endpoint: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self.tool_runner(endpoint, params)
        if not isinstance(response, Mapping):
            return {"status": "failed", "message": f"Unexpected {endpoint} response."}
        return response


_DEFAULT_PROTOCOL: Optional[AgentFMissionProtocol] = None


def configure_protocol(
    tool_runner: ToolRunner,
    code_repairer: Optional[CodeRepairer] = None,
) -> AgentFMissionProtocol:
    """Configure and return the default Agent F mission protocol instance.

    Use this once at process startup, providing a PlatformIO-MCP-aware tool
    runner. Module-level mission helpers will then delegate to this instance.
    """

    global _DEFAULT_PROTOCOL
    _DEFAULT_PROTOCOL = AgentFMissionProtocol(
        tool_runner=tool_runner,
        code_repairer=code_repairer,
    )
    return _DEFAULT_PROTOCOL


def inspect(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Call ``agent_f.inspect`` through the configured PlatformIO-MCP runner."""

    return _get_protocol().inspect(params)


def build(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Call ``agent_f.build`` through the configured PlatformIO-MCP runner."""

    return _get_protocol().build(params)


def flash(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Call ``agent_f.flash`` through the configured PlatformIO-MCP runner."""

    return _get_protocol().flash(params)


def monitor(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Call ``agent_f.monitor`` through the configured PlatformIO-MCP runner."""

    return _get_protocol().monitor(params)


def diagnose(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Call ``agent_f.diagnose`` and produce a structured Mission Report."""

    return _get_protocol().diagnose(params)


def repair(params: Mapping[str, Any]) -> Dict[str, Any]:
    """Call ``agent_f.repair``, then rebuild/reflash using mission protocol."""

    return _get_protocol().repair(params)


def _get_protocol() -> AgentFMissionProtocol:
    if _DEFAULT_PROTOCOL is None:
        raise RuntimeError(
            "Agent F protocol is not configured. "
            "Call configure_protocol(tool_runner=...) first."
        )
    return _DEFAULT_PROTOCOL


def _make_result(
    *,
    status: str,
    tool: str,
    board: Optional[str],
    environment: Optional[str],
    findings: List[Mapping[str, Any]],
    agent_f_message: str,
    mission_report: Optional[str] = None,
    data: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": status,
        "tool": tool,
        "board": board or "unknown",
        "environment": environment or "unknown",
        "findings": findings,
        "agent_f_message": agent_f_message,
        "agent_f": agent_f_message,
    }
    if mission_report is not None:
        payload["mission_report"] = mission_report
    if data is not None:
        payload["data"] = dict(data)
    return payload


def _normalize_status(value: Any, *, default: str) -> str:
    if not isinstance(value, str):
        return default
    lowered = value.strip().lower()
    if lowered in {"success", "ok", "passed"}:
        return "success"
    if lowered in {"fail", "failed", "error"}:
        return "failed"
    if lowered in {"partial", "warning", "warn"}:
        return "partial"
    return default


def _pick_board(raw: Mapping[str, Any], params: Mapping[str, Any]) -> Optional[str]:
    for key in ("board", "board_id", "target_board"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("board", "board_id", "target_board"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _pick_environment(raw: Mapping[str, Any], params: Mapping[str, Any]) -> Optional[str]:
    for key in ("environment", "env", "target_environment"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("environment", "env", "target_environment"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _as_findings(value: Any) -> List[Mapping[str, Any]]:
    if isinstance(value, list):
        findings: List[Mapping[str, Any]] = []
        for item in value:
            if isinstance(item, Mapping):
                findings.append(dict(item))
            elif isinstance(item, str) and item.strip():
                findings.append({"issue": item.strip(), "severity": "info"})
        return findings
    if isinstance(value, str) and value.strip():
        return [{"issue": value.strip(), "severity": "info"}]
    return []


def _extract_log_text(raw: Mapping[str, Any]) -> str:
    for key in ("logs", "serial_log", "output", "stdout", "text"):
        value = raw.get(key)
        if isinstance(value, str):
            return value
    return ""


def _extract_any_text(payload: Mapping[str, Any]) -> str:
    chunks: List[str] = []
    for value in payload.values():
        if isinstance(value, str):
            chunks.append(value)
        elif isinstance(value, Mapping):
            nested = _extract_any_text(value)
            if nested:
                chunks.append(nested)
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, str):
                    chunks.append(entry)
                elif isinstance(entry, Mapping):
                    nested = _extract_any_text(entry)
                    if nested:
                        chunks.append(nested)
    return "\n".join(chunks)


def _classify_findings_from_text(text: str) -> List[Mapping[str, Any]]:
    if not text:
        return []

    findings: List[Mapping[str, Any]] = []
    lowered = text.lower()
    for issue, patterns in _PATTERN_RULES.items():
        evidence = []
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

    if "error" in lowered and not findings:
        findings.append(
            {
                "issue": "unclassified runtime error",
                "severity": "warn",
                "evidence": ["error"],
            }
        )
    return findings


def _dedupe_findings(findings: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    seen = set()
    deduped: List[Mapping[str, Any]] = []
    for finding in findings:
        issue = str(finding.get("issue", "")).strip().lower()
        if not issue or issue in seen:
            continue
        seen.add(issue)
        deduped.append(finding)
    return deduped


def _render_mission_report(
    *,
    board: Optional[str],
    environment: Optional[str],
    actions: List[str],
    status: str,
    findings: List[Mapping[str, Any]],
    fixes: List[Any],
) -> str:
    finding_summary = "none"
    if findings:
        finding_summary = ", ".join(str(item.get("issue", "unknown")) for item in findings)
    fix_summary = "none"
    if fixes:
        fix_summary = ", ".join(_stringify_fix(item) for item in fixes)
    return (
        "Mission Report | "
        f"board={board or 'unknown'} | "
        f"env={environment or 'unknown'} | "
        f"actions={','.join(actions)} | "
        f"status={status} | "
        f"findings={finding_summary} | "
        f"fixes={fix_summary}"
    )


def _stringify_fix(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, Mapping):
        for key in ("summary", "issue", "action", "message"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "mapping-fix"
    return str(item)
