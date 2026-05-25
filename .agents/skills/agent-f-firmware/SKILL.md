---
name: agent-f-firmware
description: |
  Use Agent F for PlatformIO projects. Inspect board configuration, build firmware, flash devices,
  monitor serial output, diagnose common hardware mistakes, and repair code.
---

# Agent F Firmware Operations

Execute firmware work as a focused mission with a predictable flow and clear reporting.

1. Read `platformio.ini` before taking any other action.
2. Extract and confirm the active environment name, board id, framework, upload_port, monitor_speed, and upload protocol.
3. Prefer PlatformIO-MCP actions over raw shell commands whenever equivalent actions are available.
4. If project configuration is ambiguous, report the ambiguity and propose the safest explicit environment choice.

# Mission Flow

1. Inspect:
   - Run `agent_f.inspect` first and reconcile its output against `platformio.ini`.
   - Confirm board target, toolchain assumptions, and serial transport details.
2. Build:
   - Run `agent_f.build` for the selected environment.
   - Capture warnings and memory pressure indicators as findings, not noise.
3. Flash:
   - Explain a short mission plan before running `agent_f.flash`.
   - Include board, port, and expected firmware image in the plan.
4. Monitor:
   - Run `agent_f.monitor` immediately after flashing.
   - Parse boot logs and runtime logs, then classify failures.
5. Diagnose:
   - Run `agent_f.diagnose` when build/flash/runtime behavior is abnormal.
   - Convert raw errors into actionable root-cause hypotheses.
6. Repair:
   - Run `agent_f.repair` for safe, targeted fixes.
   - Rebuild and reflash after repairs, then verify with monitor logs.

# Failure Classification Checklist

Always check these embedded failure patterns explicitly:

- Strapping pin misuse.
- Wrong baud rate.
- Wrong board target.
- Missing `upload_port`.
- Unsafe GPIO selection.
- Brownout symptoms.
- Blocking `setup()` or `loop()` logic.

Use `references/esp32_strapping_pins.md` for strap-related triage and `references/platformio_workflow.md` for build/flash process discipline when those files are available in the active skill package.

# Mission Report Contract

End every workflow with a concise `Mission Report` that includes:

- Target board and environment.
- Actions taken in order.
- Current status: success, partial, or failed.
- Fixes applied and any remaining risk.

Keep the report short, factual, and operator-ready.
