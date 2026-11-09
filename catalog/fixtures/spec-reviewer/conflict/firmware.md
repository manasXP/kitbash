---
modified: 2026-03-12
---
# Rillet firmware

The firmware targets the RP2040 on the main board and supports up to 6 zones.

## Valve board link

The valve task exchanges commands with the valve board over CAN at 500 kbit/s.

## Dry-run protection

The main board's pump task decides dry-run shutdown and commands the valve board to
stop the pump. It waits 30 s after the flow sensor reads zero before stopping.
