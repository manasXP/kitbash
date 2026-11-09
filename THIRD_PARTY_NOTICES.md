# Third-party notices

The MIT License in `LICENSE` does not cover the files below. They keep their own licenses, included unmodified from upstream.

The firmware fixture at `catalog/fixtures/firmware/pdu/` includes vendor code from [STM32CubeG4](https://github.com/STMicroelectronics/STM32CubeG4) `v1.6.0`:

| Files | Component and pinned commit | License | License file |
|---|---|---|---|
| `Drivers/STM32G4xx_HAL_Driver/` | [stm32g4xx_hal_driver](https://github.com/STMicroelectronics/stm32g4xx_hal_driver) `63c724f` | BSD-3-Clause | `Drivers/STM32G4xx_HAL_Driver/LICENSE.md` |
| `Drivers/CMSIS/Device/ST/STM32G4xx/`, `Core/Src/system_stm32g4xx.c`, `Core/Src/startup_stm32g474retx.s` | [cmsis_device_g4](https://github.com/STMicroelectronics/cmsis_device_g4) `f4ee399` | Apache-2.0 | `Drivers/CMSIS/Device/ST/STM32G4xx/LICENSE.md` |
| `Drivers/CMSIS/Include/` | Arm CMSIS, as shipped in STM32CubeG4 `v1.6.0` | Apache-2.0 | `Drivers/CMSIS/LICENSE.txt` |

The scripts' fallback YAML parser at `catalog/scripts/vendor/yaml/` is the pure-Python package of [PyYAML](https://github.com/yaml/pyyaml) `6.0.3`, used only when no PyYAML is installed. It is MIT licensed; the license is at `catalog/scripts/vendor/PyYAML-LICENSE`.

Packs in `catalog/packs/` record the upstream source and license of each third-party skill set. Those skills are fetched from upstream and keep their own licenses.
