---
modified: 2026-05-11
---
# Rillet firmware

## Status message

The unit publishes a status message to the app every 10 seconds, including
`firmware_version`, `uptime_s` and `zones`, which holds each zone's name and whether it
is watering.

## Watchdog

A hardware watchdog resets the unit if the main loop stalls for 2 seconds.
