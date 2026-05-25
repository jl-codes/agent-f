# PlatformIO Mission Workflow

Use this workflow to keep build, flash, and monitor missions deterministic.

## Preflight

1. Read `platformio.ini`.
2. Confirm active `[env:...]` target.
3. Confirm `board`, `framework`, `upload_port`, and `monitor_speed`.
4. Verify that device connection and permissions are valid.

## Build

1. Run `agent_f.build` for the active environment.
2. Capture compile warnings, linker errors, and memory usage trends.
3. Stop and diagnose before flashing if build fails or warnings indicate high risk.

## Flash

1. Announce mission plan with environment, board, and upload port.
2. Run `agent_f.flash`.
3. If flash fails, classify whether the issue is port, board target, boot mode, or power integrity.

## Monitor

1. Run `agent_f.monitor` immediately after flash.
2. Validate boot messages and expected application startup behavior.
3. Parse output for known failure classes:
   - Wrong baud rate.
   - Brownout/reset loops.
   - Watchdog resets from blocking logic.
   - Strapping pin boot conflicts.

## Diagnose and Repair

1. Run `agent_f.diagnose` with build, flash, and monitor artifacts.
2. Propose smallest safe repair first.
3. For code repairs, prefer:
   - Reassigning unsafe GPIOs.
   - Adding startup delays for unstable peripherals.
   - Avoiding blocking loops in `setup()` and `loop()`.
4. Rebuild, reflash, and re-monitor after each fix.

## Mission Report Template

`Mission Report: board=<board>, env=<env>, actions=<inspect/build/flash/monitor/diagnose/repair>, status=<success|partial|failed>, fixes=<summary>`
