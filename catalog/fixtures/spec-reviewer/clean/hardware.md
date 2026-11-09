---
modified: 2026-03-12
---
# Rillet hardware

## Main board

The main board uses an RP2040. Rev A used an ESP32; rev B replaced it with the RP2040
to get a second independent UART.

The supply is sized for a 120 W peak draw.

## Valve board

The main board talks to the valve board over RS-485 at 115200 baud. Rillet Lite fits
a valve board with 2 outputs and Rillet Pro one with 6.

Each zone valve passes at most 30 L/min.

## Dry-run protection

The pump stops within 5 s of the flow sensor reading zero, to protect the pump seal.
The valve board decides this shutdown locally, so it still works if the main board hangs.
