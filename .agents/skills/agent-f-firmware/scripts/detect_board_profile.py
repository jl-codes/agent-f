#!/usr/bin/env python3
"""Detect board profiles from a PlatformIO project configuration."""

from __future__ import annotations

import argparse
import configparser
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_platformio_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str.lower
    with path.open("r", encoding="utf-8") as handle:
        parser.read_file(handle)
    return parser


def select_default_env(config: configparser.ConfigParser) -> Optional[str]:
    if config.has_section("platformio"):
        raw = config.get("platformio", "default_envs", fallback="").strip()
        if raw:
            return raw.split(",")[0].strip()
    envs = [
        section.replace("env:", "", 1)
        for section in config.sections()
        if section.startswith("env:")
    ]
    if len(envs) == 1:
        return envs[0]
    return None


def extract_env_profiles(config: configparser.ConfigParser) -> List[Dict[str, Any]]:
    profiles: List[Dict[str, Any]] = []
    for section in config.sections():
        if not section.startswith("env:"):
            continue
        env_name = section.replace("env:", "", 1)
        profile = {
            "environment": env_name,
            "board": config.get(section, "board", fallback=""),
            "framework": config.get(section, "framework", fallback=""),
            "upload_port": config.get(section, "upload_port", fallback=""),
            "upload_protocol": config.get(section, "upload_protocol", fallback=""),
            "monitor_speed": config.get(section, "monitor_speed", fallback=""),
        }
        profile["findings"] = collect_profile_findings(profile)
        profiles.append(profile)
    return profiles


def collect_profile_findings(profile: Dict[str, Any]) -> List[str]:
    findings = []
    if not profile.get("board"):
        findings.append("missing board target")
    if not profile.get("framework"):
        findings.append("missing framework")
    if not profile.get("upload_port"):
        findings.append("missing upload_port")
    if not profile.get("monitor_speed"):
        findings.append("missing monitor_speed (baud may be ambiguous)")
    return findings


def build_report(path: Path, explicit_env: Optional[str]) -> Dict[str, Any]:
    config = parse_platformio_ini(path)
    profiles = extract_env_profiles(config)
    default_env = explicit_env or select_default_env(config)

    active_profile = None
    if default_env:
        for profile in profiles:
            if profile["environment"] == default_env:
                active_profile = profile
                break

    return {
        "status": "success" if profiles else "failed",
        "tool": "detect_board_profile.py",
        "board": active_profile["board"] if active_profile else "unknown",
        "active_environment": default_env,
        "profiles": profiles,
        "agent_f_message": (
            f"Detected {len(profiles)} environment profile(s); "
            f"active environment is '{default_env or 'not set'}'."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ini",
        default="platformio.ini",
        help="Path to platformio.ini (default: %(default)s)",
    )
    parser.add_argument(
        "--env",
        default=None,
        help="Explicit environment name to mark as active.",
    )
    args = parser.parse_args()

    ini_path = Path(args.ini).resolve()
    if not ini_path.exists():
        print(
            json.dumps(
                {
                    "status": "failed",
                    "tool": "detect_board_profile.py",
                    "board": "unknown",
                    "findings": ["platformio.ini not found"],
                    "agent_f_message": f"Missing file: {ini_path}",
                },
                indent=2,
            )
        )
        return 1

    report = build_report(ini_path, args.env)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
