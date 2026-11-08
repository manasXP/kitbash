#!/usr/bin/env bash
# flash.sh — program the board over SWD with an ST-Link probe.
#
# Needs st-flash (open-source stlink) or STM32_Programmer_CLI (STM32CubeProgrammer)
# on PATH and a probe attached. Builds first if the hex is missing.
set -euo pipefail
cd "$(dirname "$0")/.."

HEX=build/pdu-firmware.hex
[ -f "$HEX" ] || ./scripts/build.sh

if command -v st-flash >/dev/null 2>&1; then
    exec st-flash --format ihex write "$HEX"
elif command -v STM32_Programmer_CLI >/dev/null 2>&1; then
    exec STM32_Programmer_CLI -c port=SWD -w "$HEX" -v -rst
fi
echo "flash: no programmer found (st-flash or STM32_Programmer_CLI not on PATH)." >&2
echo "flash: install stlink or STM32CubeProgrammer and connect an ST-Link probe, then rerun." >&2
exit 2
