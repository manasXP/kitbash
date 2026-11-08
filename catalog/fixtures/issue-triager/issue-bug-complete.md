# Date picker shows wrong month after timezone change

**Version:** 4.2.1
**Environment:** macOS 15.1, Chrome 131

**Steps to reproduce**
1. Set system timezone to UTC-8.
2. Open Settings > Schedule and select 31 Jan.
3. Change system timezone to UTC+9 and reload.

**Expected:** picker shows January 31.
**Actual:** picker shows February 1 highlighted in January's grid.

Workaround: re-selecting the date fixes it until the next reload.
