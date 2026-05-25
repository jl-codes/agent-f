# ESP32 Strapping Pin Reference

Use this reference when boot issues, random resets, or flash failures indicate pin-state problems.

## Why Strapping Pins Matter

ESP32 samples several GPIO levels at reset to decide boot mode and voltage behavior. External circuits that pull these pins the wrong way can block boot or cause unstable startup.

## Common Risk Pins

- GPIO0: Low at reset can enter bootloader mode.
- GPIO2: Must be in a valid boot state; aggressive pull-ups or pull-downs can break startup.
- GPIO12 (MTDI): Wrong level can force invalid flash voltage behavior on some modules.
- GPIO15 and related boot pins: board-specific constraints may apply.

## Triage Pattern

1. Review schematic and code for any external pull or forced output on strap pins.
2. Check startup logs for `boot mode`, repeated reset, or ROM bootloader output.
3. Remove or isolate peripherals on strap pins and retry flash/boot.
4. Move application signals away from strap pins where possible.

## Safe Practice

- Reserve strap pins for passive, reset-safe usage only.
- Prefer non-strap GPIOs for relays, chip-select, and peripheral enable lines.
- Add power-on delays for external peripherals if they can influence strap levels at reset.
