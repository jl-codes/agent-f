"""End-to-end examples validating Agent F as a skill and protocol."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import unittest

from agent_f.protocol import build
from agent_f.protocol import configure_protocol
from agent_f.protocol import diagnose
from agent_f.protocol import flash
from agent_f.protocol import inspect
from agent_f.protocol import monitor
from agent_f.protocol import repair
from tests.e2e.runner_utils import DEFAULT_ENVIRONMENT
from tests.e2e.runner_utils import FakeAgentFRunner
from tests.e2e.runner_utils import classify_common_issues
from tests.e2e.runner_utils import load_fixture_text
from tests.e2e.runner_utils import resolve_live_runner

ROOT_DIR = Path(__file__).resolve().parents[2]
README_PATH = ROOT_DIR / "README.md"
SKILL_ROOT_PATH = ROOT_DIR / "SKILL.md"
PACKAGED_SKILL_PATH = ROOT_DIR / ".agents" / "skills" / "agent-f-firmware" / "SKILL.md"
PACKAGED_SKILL_DIR = PACKAGED_SKILL_PATH.parent
PACKAGED_BANNER_PATH = PACKAGED_SKILL_DIR / "assets" / "agent-f-banner.txt"
README_IMAGE_PATH = ROOT_DIR / "assets" / "AgentF-PlatformIO-MCP.png"
FIXTURE_PROJECT_DIR = ROOT_DIR / "tests" / "e2e" / "fixtures" / "project_minimal"
FIXTURE_LOG_DIR = ROOT_DIR / "tests" / "e2e" / "fixtures" / "logs"

NORMAL_BOOT_LOG = FIXTURE_LOG_DIR / "normal_boot.log"
BROWNOUT_LOG = FIXTURE_LOG_DIR / "brownout_reset.log"
WATCHDOG_LOG = FIXTURE_LOG_DIR / "watchdog_blocking.log"
BROWNOUT_AND_STRAP_LOG = FIXTURE_LOG_DIR / "brownout_strapping_watchdog.log"


def _base_params() -> dict:
    return {
        "project_dir": str(FIXTURE_PROJECT_DIR),
        "environment": DEFAULT_ENVIRONMENT,
        "board": "esp32dev",
        "upload_port": "COM5",
        "baud": 115200,
    }


class AgentFSkillPackageE2ETest(unittest.TestCase):
    def _assert_portrait_structure(
        self,
        ascii_block: str,
        *,
        min_lines: int,
        context_label: str,
    ) -> None:
        lines = [line.rstrip("\n") for line in ascii_block.splitlines() if line.strip()]
        self.assertGreaterEqual(
            len(lines),
            min_lines,
            f"{context_label}: portrait is too short.",
        )
        self.assertLessEqual(
            max(len(line) for line in lines),
            110,
            f"{context_label}: portrait exceeds 110 columns.",
        )
        diversity = {ch for ch in "".join(lines) if not ch.isspace()}
        self.assertGreaterEqual(
            len(diversity),
            12,
            f"{context_label}: portrait character diversity is too low.",
        )

        pillar_lines = sum(1 for line in lines if "||" in line)
        self.assertGreaterEqual(
            pillar_lines,
            8,
            f"{context_label}: expected stronger coat/stance geometry (missing '||' pillars).",
        )

        motif_groups = {
            "hair": [".--..--.", "( \\/ )", ".-____-."],
            "collar": ["/ /\\ \\", "|  `-..-'  |", ".- \\/ -."],
            "coat": [".------------.", ".--------.", "/_/    \\_\\"],
        }
        for group_name, options in motif_groups.items():
            self.assertTrue(
                any(option in ascii_block for option in options),
                f"{context_label}: missing {group_name} motif markers.",
            )

    def test_skill_frontmatter_and_required_directives(self) -> None:
        root_text = SKILL_ROOT_PATH.read_text(encoding="utf-8")
        packaged_text = PACKAGED_SKILL_PATH.read_text(encoding="utf-8")

        self.assertEqual(root_text, packaged_text)
        self.assertTrue(root_text.startswith("---\n"), "SKILL frontmatter must start with '---'.")

        required_frontmatter_lines = [
            "name: agent-f-firmware",
            "Use Agent F for PlatformIO projects. Inspect board configuration, build firmware, flash devices,",
        ]
        for expected in required_frontmatter_lines:
            self.assertIn(expected, root_text)

        required_directives = [
            "Read `platformio.ini` before taking any other action.",
            "Prefer PlatformIO-MCP actions over raw shell commands whenever equivalent actions are available.",
            "Explain a short mission plan before running `agent_f.flash`.",
            "Run `agent_f.monitor` immediately after flashing.",
            "End every workflow with a concise `Mission Report`",
        ]
        for directive in required_directives:
            self.assertIn(directive, root_text)

    def test_packaged_skill_assets_and_references_exist(self) -> None:
        required_paths = [
            PACKAGED_SKILL_DIR / "AGENTS.md",
            PACKAGED_BANNER_PATH,
            PACKAGED_SKILL_DIR / "scripts" / "detect_board_profile.py",
            PACKAGED_SKILL_DIR / "scripts" / "summarize_serial_log.py",
            PACKAGED_SKILL_DIR / "references" / "esp32_strapping_pins.md",
            PACKAGED_SKILL_DIR / "references" / "platformio_workflow.md",
        ]
        for path in required_paths:
            self.assertTrue(path.exists(), f"Expected packaged path to exist: {path}")

    def test_e2e_log_fixtures_exist(self) -> None:
        for path in [NORMAL_BOOT_LOG, BROWNOUT_LOG, WATCHDOG_LOG, BROWNOUT_AND_STRAP_LOG]:
            self.assertTrue(path.exists(), f"Missing e2e log fixture: {path}")

    def test_packaged_helper_scripts_have_working_help_flags(self) -> None:
        scripts = [
            PACKAGED_SKILL_DIR / "scripts" / "detect_board_profile.py",
            PACKAGED_SKILL_DIR / "scripts" / "summarize_serial_log.py",
        ]
        for script_path in scripts:
            result = subprocess.run(
                ["python", str(script_path), "--help"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("usage:", result.stdout.lower())

    def test_codex_pet_banner_and_readme_contract(self) -> None:
        banner_text = PACKAGED_BANNER_PATH.read_text(encoding="utf-8")
        readme_text = README_PATH.read_text(encoding="utf-8")

        self.assertTrue(README_IMAGE_PATH.exists(), f"Missing README image asset: {README_IMAGE_PATH}")
        self.assertIn("![Agent F PlatformIO-MCP](assets/AgentF-PlatformIO-MCP.png)", readme_text)
        self.assertIn("**AGENT F**", readme_text)
        self.assertIn("`PlatformIO-MCP Firmware Agent`", readme_text)
        self.assertIn("Mission profile: `build -> flash -> monitor -> diagnose -> repair`", readme_text)

        readme_code_blocks = re.findall(r"```text\n(.*?)\n```", readme_text, flags=re.DOTALL)
        self.assertGreaterEqual(len(readme_code_blocks), 1, "README must contain a text portrait block.")
        readme_portrait = readme_code_blocks[0]

        self._assert_portrait_structure(
            readme_portrait,
            min_lines=40,
            context_label="README portrait",
        )
        self._assert_portrait_structure(
            banner_text,
            min_lines=30,
            context_label="CLI banner portrait",
        )


class AgentFMissionOfflineE2ETest(unittest.TestCase):
    def _assert_protocol_payload(self, payload: dict, expected_tool: str) -> None:
        required_keys = {
            "status",
            "tool",
            "board",
            "environment",
            "findings",
            "agent_f_message",
        }
        self.assertTrue(required_keys.issubset(payload.keys()))
        self.assertEqual(payload["tool"], expected_tool)
        self.assertIsInstance(payload["findings"], list)
        self.assertIsInstance(payload["agent_f_message"], str)

    def test_offline_happy_path_full_mission_chain(self) -> None:
        fake_runner = FakeAgentFRunner(monitor_log=load_fixture_text(NORMAL_BOOT_LOG))
        applied_repairs = []

        def fake_code_repairer(_raw: dict) -> dict:
            applied_repairs.append("called")
            return {"summary": "Applied boot stabilization delay."}

        configure_protocol(tool_runner=fake_runner, code_repairer=fake_code_repairer)

        params = _base_params()
        inspect_result = inspect(params)
        build_result = build(params)
        flash_result = flash(params)
        monitor_result = monitor(params)
        diagnose_result = diagnose(
            {**params, "context": {"build": build_result, "flash": flash_result, "logs": monitor_result}}
        )
        repair_result = repair({**params, "allow_code_changes": True})

        self._assert_protocol_payload(inspect_result, "agent_f.inspect")
        self._assert_protocol_payload(build_result, "agent_f.build")
        self._assert_protocol_payload(flash_result, "agent_f.flash")
        self._assert_protocol_payload(monitor_result, "agent_f.monitor")
        self._assert_protocol_payload(diagnose_result, "agent_f.diagnose")
        self._assert_protocol_payload(repair_result, "agent_f.repair")

        self.assertIn("mission_report", diagnose_result)
        self.assertIn("Mission Report | board=esp32dev | env=esp32dev", diagnose_result["mission_report"])
        self.assertIn("mission_report", repair_result)
        self.assertEqual(len(applied_repairs), 1, "Expected code_repairer to run once.")

        expected_sequence = [
            "agent_f.inspect",
            "agent_f.build",
            "agent_f.flash",
            "agent_f.monitor",
            "agent_f.diagnose",
            "agent_f.repair",
            "agent_f.build",
            "agent_f.flash",
        ]
        self.assertEqual(fake_runner.calls, expected_sequence)

    def test_offline_failure_triage_detects_common_hardware_patterns(self) -> None:
        fake_runner = FakeAgentFRunner(monitor_log=load_fixture_text(BROWNOUT_AND_STRAP_LOG))
        configure_protocol(tool_runner=fake_runner)

        params = _base_params()
        monitor_result = monitor(params)
        diagnose_result = diagnose({**params, "context": {"logs": monitor_result}})

        findings_by_issue = {item["issue"]: item for item in diagnose_result["findings"]}
        self.assertIn("strapping pin misuse", findings_by_issue)
        self.assertIn("brownout symptoms", findings_by_issue)
        self.assertIn("blocking setup()/loop() logic", findings_by_issue)
        self.assertIn(
            findings_by_issue["brownout symptoms"]["severity"],
            {"high", "warn"},
            "Brownout issue should be high or warn severity.",
        )
        self.assertIn("Mission Report |", diagnose_result["mission_report"])

    def test_offline_repair_orchestration_merges_fixes(self) -> None:
        fake_runner = FakeAgentFRunner(monitor_log=load_fixture_text(BROWNOUT_AND_STRAP_LOG))

        def fake_code_repairer(_raw: dict) -> dict:
            return {"summary": "Moved relay pin away from GPIO0."}

        configure_protocol(tool_runner=fake_runner, code_repairer=fake_code_repairer)
        result = repair({**_base_params(), "allow_code_changes": True})

        self._assert_protocol_payload(result, "agent_f.repair")
        self.assertEqual(result["status"], "partial")
        self.assertIn("Mission Report |", result["mission_report"])
        self.assertIn("fixes=", result["mission_report"])
        nested = result.get("data", {})
        self.assertIn("build", nested)
        self.assertIn("flash", nested)
        self.assertTrue(nested.get("fixes_applied"))

        classified = classify_common_issues(load_fixture_text(BROWNOUT_AND_STRAP_LOG))
        self.assertGreaterEqual(len(classified), 2)


class AgentFLiveSmokeE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("AGENT_F_E2E_LIVE", "").strip() != "1":
            raise unittest.SkipTest("Set AGENT_F_E2E_LIVE=1 to enable live smoke tests.")

        project_dir = os.getenv("AGENT_F_E2E_PROJECT_DIR", "").strip()
        if project_dir:
            cls.project_dir = Path(project_dir).resolve()
        else:
            cls.project_dir = FIXTURE_PROJECT_DIR

        cls.environment = os.getenv("AGENT_F_E2E_ENV", DEFAULT_ENVIRONMENT).strip()
        cls.upload_port = os.getenv("AGENT_F_E2E_UPLOAD_PORT", "").strip()
        cls.monitor_baud = os.getenv("AGENT_F_E2E_MONITOR_BAUD", "").strip()

        context = resolve_live_runner(cls.project_dir)
        cls.live_context = context
        configure_protocol(tool_runner=context.runner)

    def _live_params(self) -> dict:
        params = {
            "project_dir": str(self.project_dir),
            "environment": self.environment,
            "board": "esp32dev",
        }
        if self.upload_port:
            params["upload_port"] = self.upload_port
        if self.monitor_baud:
            params["baud"] = int(self.monitor_baud)
        return params

    def test_live_inspect_build_diagnose_smoke(self) -> None:
        params = self._live_params()

        inspect_result = inspect(params)
        build_result = build(params)
        diagnose_result = diagnose(
            {
                **params,
                "context": {
                    "build": build_result,
                    "logs": "Live smoke path executed for agent-f.",
                },
            }
        )

        self.assertIn(inspect_result["status"], {"success", "partial"})
        self.assertIn(build_result["status"], {"success", "partial"})
        self.assertIn(diagnose_result["status"], {"success", "partial", "failed"})
        self.assertEqual(inspect_result["tool"], "agent_f.inspect")
        self.assertEqual(build_result["tool"], "agent_f.build")
        self.assertEqual(diagnose_result["tool"], "agent_f.diagnose")

    def test_live_flash_monitor_optional_hardware_path(self) -> None:
        if not self.live_context.supports_flash_monitor:
            self.skipTest(
                "Flash/monitor smoke skipped: "
                f"{self.live_context.detail}"
            )

        params = self._live_params()
        if "upload_port" not in params or "baud" not in params:
            self.skipTest(
                "Flash/monitor smoke skipped: both AGENT_F_E2E_UPLOAD_PORT "
                "and AGENT_F_E2E_MONITOR_BAUD are required."
            )

        flash_result = flash(params)
        monitor_result = monitor({**params, "port": params["upload_port"]})
        self.assertIn(flash_result["status"], {"success", "partial"})
        self.assertIn(monitor_result["status"], {"success", "partial"})
