# Agent F Firmware Skill

![Agent F PlatformIO-MCP](assets/AgentF-PlatformIO-MCP.png)

Agent F is a firmware-focused Codex skill for PlatformIO projects. It exists to make embedded workflows reliable and repeatable by enforcing a mission protocol:

`inspect -> build -> flash -> monitor -> diagnose -> repair`

Agent F is opinionated about preflight checks, serial-log triage, and concise reporting so teams can move from "board not responding" to a verified fix faster.

```text
   .-""""-.
  /  .--.  \      Agent F
 |  (o  o)  |     PlatformIO-MCP Firmware Agent
 |   \__/   |     > build  > flash  > monitor
  \ .____. /      > analyze > repair > report
   /|_  _|\       (cute but ruthless about bugs)
  /_/ \/ \_\
    /_/\_\
```

## What is included

- Root skill definition: `SKILL.md`
- Agent persona and invocation guide: `AGENTS.md`
- Packaged reusable skill:
  - `.agents/skills/agent-f-firmware/SKILL.md`
  - `.agents/skills/agent-f-firmware/assets/agent-f-banner.txt`
  - `.agents/skills/agent-f-firmware/scripts/*.py`
  - `.agents/skills/agent-f-firmware/references/*.md`
- Mission protocol module:
  - `agent_f/protocol.py`

## Install the skill in another project

Copy the packaged skill folder into the target project:

```powershell
Copy-Item -Recurse -Force `
  ".\.agents\skills\agent-f-firmware" `
  "C:\path\to\your-project\.agents\skills\agent-f-firmware"
```

If your Codex setup discovers skills from a shared location, copy the same folder there instead.

## Use with Codex

When the skill is active, Codex should:

1. Read `platformio.ini` first.
2. Prefer PlatformIO-MCP actions over raw shell commands.
3. Explain the flash mission plan before flashing.
4. Monitor serial logs after flashing and classify failures.
5. End with a concise Mission Report.

### Example mission workflow (tool-level)

```python
inspect_result = agent_f.inspect({"project_dir": ".", "environment": "esp32dev"})
build_result = agent_f.build({"project_dir": ".", "environment": "esp32dev"})
flash_result = agent_f.flash({"project_dir": ".", "environment": "esp32dev", "upload_port": "COM5"})
monitor_result = agent_f.monitor({"project_dir": ".", "environment": "esp32dev", "port": "COM5", "baud": 115200})
diagnosis_result = agent_f.diagnose({
    "project_dir": ".",
    "environment": "esp32dev",
    "context": {"build": build_result, "flash": flash_result, "logs": monitor_result},
})
repair_result = agent_f.repair({
    "project_dir": ".",
    "environment": "esp32dev",
    "diagnosis": diagnosis_result,
    "allow_code_changes": True,
})
```

### Example mission workflow (Python protocol module)

```python
from agent_f.protocol import configure_protocol, inspect, build, flash, monitor, diagnose, repair

def run_platformio_mcp(endpoint, params):
    # Replace with your MCP client/tool dispatcher.
    return {"status": "success", "tool": endpoint, "board": params.get("board", "esp32dev")}

configure_protocol(tool_runner=run_platformio_mcp)

inspect_result = inspect({"project_dir": ".", "environment": "esp32dev"})
build_result = build({"project_dir": ".", "environment": "esp32dev"})
flash_result = flash({"project_dir": ".", "environment": "esp32dev", "upload_port": "COM5"})
monitor_result = monitor({"project_dir": ".", "environment": "esp32dev", "port": "COM5", "baud": 115200})
diagnosis_result = diagnose({"context": {"build": build_result, "flash": flash_result, "logs": monitor_result}})
repair_result = repair({"environment": "esp32dev", "allow_code_changes": False})
```

## Environment requirements

- PlatformIO project with a valid `platformio.ini`
- PlatformIO-MCP server available to Codex
- Connected target board and usable serial/upload port

The helper scripts use only Python standard library modules, so no extra dependencies are required.

## End-to-end test suite

This repository includes a fully e2e example suite under `tests/e2e` that validates:

1. Skill package contract (`SKILL.md`, packaged resources, helper scripts).
2. Mission protocol behavior (`inspect -> build -> flash -> monitor -> diagnose -> repair`).
3. Failure classification and repair orchestration.

### Run tests (offline deterministic path)

```powershell
python -m unittest discover -s tests -p "test*.py"
```

If `pytest` is installed, the same suite can run via:

```powershell
pytest tests/e2e -q
```

### Optional live smoke mode

Live smoke is opt-in and disabled by default.

```powershell
$env:AGENT_F_E2E_LIVE = "1"
python -m unittest discover -s tests -p "test*.py"
```

Environment variables:

- `AGENT_F_E2E_LIVE=1` enables live smoke tests.
- `AGENT_F_E2E_TOOL_RUNNER=package.module:function` selects a preferred adapter callable with signature `(endpoint: str, params: Mapping[str, Any]) -> Mapping[str, Any]`.
- `AGENT_F_E2E_PROJECT_DIR` optionally points to a real PlatformIO project.
- `AGENT_F_E2E_ENV` selects the target environment (defaults to `esp32dev`).
- `AGENT_F_E2E_UPLOAD_PORT` and `AGENT_F_E2E_MONITOR_BAUD` enable flash/monitor hardware smoke.

Live runner resolution:

1. Use adapter from `AGENT_F_E2E_TOOL_RUNNER` when provided.
2. Otherwise fall back to `pio` CLI reduced smoke (`inspect/build/diagnose` only).
3. Skip flash/monitor with an explicit reason when hardware variables are not set.
