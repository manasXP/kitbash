---
modified: 2026-03-12
---
# Rillet firmware

The firmware targets the RP2040 on the main board and supports up to 6 zones.

## Valve board link

The valve task exchanges commands with the valve board over RS-485 at 115200 baud.

## Dry-run protection

The valve board stops the pump on its own within 5 s of the flow sensor reading zero
and then reports the shutdown to the main board, which logs it and raises an alert.

## Logging

Events are kept in a ring buffer of 256 entries.
