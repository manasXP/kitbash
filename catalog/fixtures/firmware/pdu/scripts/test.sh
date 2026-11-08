#!/usr/bin/env bash
# test.sh — smoke test. The project has no unit-test framework yet (see README).
#
# 1. Builds with ./scripts/build.sh (project-source warnings are errors).
# 2. Checks the ELF: vector table at the start of flash, Reset_Handler present,
#    flash and RAM usage under 90 % of the STM32G474RE budgets.
set -euo pipefail
cd "$(dirname "$0")/.."

./scripts/build.sh "$@"

for cand in "${PREFIX:-}" "$HOME/.local/arm-gnu-toolchain/bin/arm-none-eabi-" "arm-none-eabi-"; do
    if [ -n "$cand" ] && command -v "${cand}readelf" >/dev/null 2>&1; then
        READELF="${cand}readelf"
        SIZE="${cand}size"
        break
    fi
done
: "${READELF:?no arm-none-eabi-readelf found}"

ELF=build/pdu-firmware.elf
fail=0
check() { if eval "$2"; then echo "ok    $1"; else echo "FAIL  $1"; fail=1; fi; }

# grep without -q: with pipefail, an early exit would SIGPIPE readelf and fail the check.
check "vector table at 0x08000000" "$READELF -S $ELF | grep '\.isr_vector *PROGBITS *08000000' >/dev/null"
check "Reset_Handler is defined"   "$READELF -s $ELF | grep ' Reset_Handler\$' >/dev/null"

read -r text data bss _ < <("$SIZE" "$ELF" | awk 'NR==2 {print $1, $2, $3}')
flash_used=$((text + data)); flash_max=$((508 * 1024 * 9 / 10))
ram_used=$((data + bss));    ram_max=$((128 * 1024 * 9 / 10))
check "flash usage ${flash_used} B under 90 % of 508 KiB" "[ $flash_used -le $flash_max ]"
check "RAM usage ${ram_used} B under 90 % of 128 KiB"     "[ $ram_used -le $ram_max ]"

if [ "$fail" -ne 0 ]; then echo "test: FAILED" >&2; exit 1; fi
echo "test: OK (4 checks)"
