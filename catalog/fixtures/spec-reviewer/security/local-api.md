---
modified: 2026-05-05
---
# Rillet local API

The unit serves this API over HTTP on the local network. No endpoint requires
authentication.

| Endpoint | Returns |
|---|---|
| `GET /status` | Firmware version and uptime |
| `GET /zones` | Zone names and schedules |
| `GET /setup/pin` | The current setup PIN |
