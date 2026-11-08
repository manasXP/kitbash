---
name: stm32-firmware
description: Write and review STM32 firmware using the HAL, with MISRA C habits and safe interrupt and DMA handling.
requires:
  tools: [Read, Edit, Bash]
  capabilities: [embedded-toolchain]
---
# STM32 firmware

## Non-negotiables

- Any variable shared between an ISR and main context is `volatile` and, if wider
  than the bus, accessed under a critical section or with an atomic.
- Every HAL call that returns `HAL_StatusTypeDef` has its result checked.
- No dynamic allocation after `main()` starts.
- Buffers handed to DMA are aligned and live for the whole transfer.
- Delays in ISRs are forbidden. ISRs set flags or push to a queue and return.

## Procedure for a change

1. Read the `.ioc` or CubeMX-generated init code before touching a peripheral,
   so the clock tree and pin assignments are known.
2. Make the change in user code regions only. Never edit between
   `USER CODE BEGIN` and `USER CODE END` markers from the generated side.
3. Build with the project's toolchain command and treat warnings as errors.
4. If a unit test harness exists, add or extend a test for the changed logic.

## Reporting

State what changed, what was built, and the exact build command that ran.
