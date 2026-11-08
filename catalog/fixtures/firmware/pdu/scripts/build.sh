#!/usr/bin/env bash
# build.sh — build the firmware with warnings in project sources treated as errors.
#
# Usage: ./scripts/build.sh [extra make args, e.g. RELEASE=1]
#
# Picks the first arm-none-eabi toolchain that ships newlib (nano.specs):
#   1. $PREFIX if set (e.g. PREFIX=/opt/arm/bin/arm-none-eabi-)
#   2. ~/.local/arm-gnu-toolchain/bin/arm-none-eabi-
#   3. arm-none-eabi-gcc on PATH
# Homebrew's arm-none-eabi-gcc has no C library and cannot link this project.
set -uo pipefail
cd "$(dirname "$0")/.."

has_newlib() { [ -f "$("${1}gcc" -print-file-name=nano.specs 2>/dev/null)" ]; }

if [ -z "${PREFIX:-}" ]; then
    for cand in "$HOME/.local/arm-gnu-toolchain/bin/arm-none-eabi-" "arm-none-eabi-"; do
        if command -v "${cand}gcc" >/dev/null 2>&1 && has_newlib "$cand"; then
            PREFIX="$cand"
            break
        fi
    done
fi
if [ -z "${PREFIX:-}" ] || ! has_newlib "$PREFIX"; then
    echo "build: no arm-none-eabi toolchain with newlib found; set PREFIX=/path/to/arm-none-eabi-" >&2
    exit 2
fi

jobs=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
log=$(mktemp)
make clean >/dev/null          # full rebuild every time, so warnings cannot hide behind up-to-date objects
make -j"$jobs" PREFIX="$PREFIX" all "$@" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}

# Warnings in our own sources fail the build. Vendor (Drivers/) and linker stub warnings do not.
warnings=$(grep -E '^(Core|App)/[^ ]+:[0-9]+:[0-9]+: warning:' "$log" | wc -l | tr -d ' ')
rm -f "$log"
if [ "$status" -ne 0 ]; then
    echo "build: FAILED (make exit $status)" >&2
    exit "$status"
fi
if [ "$warnings" -ne 0 ]; then
    echo "build: FAILED ($warnings warning(s) in Core/ or App/; warnings are errors here)" >&2
    exit 1
fi
echo "build: OK ($("${PREFIX}gcc" --version | head -1))"
