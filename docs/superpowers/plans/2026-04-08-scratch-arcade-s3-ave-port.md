# Scratch Arcade S3 AVE Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `scratch-arcade-s3` firmware target that can render the AVE simulator screens on Scratch Arcade hardware and package a flashable `merged-binary.bin`.

**Architecture:** Keep the existing xiaozhi firmware runtime intact, then add a narrow AVE bridge layer for three responsibilities only: board registration, server `type=display` ingestion, and button-to-AVE event dispatch. Reuse the current `shared/ave_screens/` rendering code and current server `type=display` protocol rather than forking a second UI implementation. Treat microphone support as a hardware validation gate because the cloned `arcade-lite` open-source docs expose LCD, key, and speaker pins, but do not confirm a Lite microphone input path.

**Tech Stack:** ESP-IDF 5.4+, C/C++, LVGL, ESP LCD SPI, existing xiaozhi firmware board framework, shared AVE C screens, Python guard tests, `idf.py`, `scripts/release.py`

---

### Task 1: Add Scratch Arcade S3 board profile and registration

**Files:**
- Create: `firmware/main/boards/scratch-arcade-s3/config.h`
- Create: `firmware/main/boards/scratch-arcade-s3/config.json`
- Create: `firmware/main/boards/scratch-arcade-s3/README.md`
- Create: `firmware/tests/test_scratch_arcade_board_profile.py`
- Modify: `firmware/main/Kconfig.projbuild`
- Modify: `firmware/main/CMakeLists.txt`

- [ ] **Step 1: Write the failing board-profile guard test**

```python
from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ScratchArcadeBoardProfileTest(unittest.TestCase):
    def test_board_profile_is_registered(self):
        kconfig = (ROOT / "main" / "Kconfig.projbuild").read_text(encoding="utf-8")
        cmake = (ROOT / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
        cfg_path = ROOT / "main" / "boards" / "scratch-arcade-s3" / "config.json"

        self.assertTrue(cfg_path.exists(), "scratch-arcade-s3 config.json missing")
        self.assertIn("CONFIG_BOARD_TYPE_SCRATCH_ARCADE_S3", kconfig)
        self.assertIn('set(BOARD_TYPE "scratch-arcade-s3")', cmake)

    def test_default_gpio_matches_arcade_lite_reference(self):
        header = (ROOT / "main" / "boards" / "scratch-arcade-s3" / "config.h").read_text(encoding="utf-8")
        expected = {
            "DISPLAY_SPI_SCK_PIN": "GPIO_NUM_12",
            "DISPLAY_SPI_MOSI_PIN": "GPIO_NUM_11",
            "DISPLAY_SPI_CS_PIN": "GPIO_NUM_10",
            "DISPLAY_DC_PIN": "GPIO_NUM_45",
            "DISPLAY_RST_PIN": "GPIO_NUM_46",
            "DISPLAY_BACKLIGHT_PIN": "GPIO_NUM_21",
            "DPAD_UP_BUTTON_GPIO": "GPIO_NUM_16",
            "DPAD_RIGHT_BUTTON_GPIO": "GPIO_NUM_15",
            "DPAD_DOWN_BUTTON_GPIO": "GPIO_NUM_14",
            "DPAD_LEFT_BUTTON_GPIO": "GPIO_NUM_13",
            "FN_BUTTON_GPIO": "GPIO_NUM_0",
            "A_BUTTON_GPIO": "GPIO_NUM_39",
            "B_BUTTON_GPIO": "GPIO_NUM_5",
            "X_BUTTON_GPIO": "GPIO_NUM_9",
            "Y_BUTTON_GPIO": "GPIO_NUM_4",
        }
        for name, value in expected.items():
            self.assertIn(f"#define {name} {value}", header)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the guard test and verify RED**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
python3 -m unittest tests/test_scratch_arcade_board_profile.py -v
```

Expected: FAIL because `scratch-arcade-s3` files and registration do not exist yet.

- [ ] **Step 3: Add the minimal board profile files**

`firmware/main/boards/scratch-arcade-s3/config.h`

```c
#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

#define AUDIO_INPUT_SAMPLE_RATE 24000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000

/* TODO after hardware validation: replace these placeholders with the
 * real microphone / codec pins if the target board exposes audio input. */
#define AUDIO_I2S_GPIO_MCLK GPIO_NUM_NC
#define AUDIO_I2S_GPIO_WS GPIO_NUM_42
#define AUDIO_I2S_GPIO_BCLK GPIO_NUM_41
#define AUDIO_I2S_GPIO_DIN GPIO_NUM_NC
#define AUDIO_I2S_GPIO_DOUT GPIO_NUM_1

#define DISPLAY_WIDTH 320
#define DISPLAY_HEIGHT 240
#define DISPLAY_SWAP_XY true
#define DISPLAY_MIRROR_X false
#define DISPLAY_MIRROR_Y true
#define DISPLAY_OFFSET_X 0
#define DISPLAY_OFFSET_Y 0
#define DISPLAY_INVERT_COLOR true
#define DISPLAY_RGB_ORDER_COLOR LCD_RGB_ELEMENT_ORDER_RGB

#define DISPLAY_SPI_LCD_HOST SPI2_HOST
#define DISPLAY_SPI_CLOCK_HZ (40 * 1000 * 1000)
#define DISPLAY_SPI_SCK_PIN GPIO_NUM_12
#define DISPLAY_SPI_MOSI_PIN GPIO_NUM_11
#define DISPLAY_SPI_MISO_PIN GPIO_NUM_NC
#define DISPLAY_SPI_CS_PIN GPIO_NUM_10
#define DISPLAY_DC_PIN GPIO_NUM_45
#define DISPLAY_RST_PIN GPIO_NUM_46
#define DISPLAY_BACKLIGHT_PIN GPIO_NUM_21
#define DISPLAY_BACKLIGHT_OUTPUT_INVERT false

#define DPAD_UP_BUTTON_GPIO GPIO_NUM_16
#define DPAD_RIGHT_BUTTON_GPIO GPIO_NUM_15
#define DPAD_DOWN_BUTTON_GPIO GPIO_NUM_14
#define DPAD_LEFT_BUTTON_GPIO GPIO_NUM_13
#define FN_BUTTON_GPIO GPIO_NUM_0
#define A_BUTTON_GPIO GPIO_NUM_39
#define B_BUTTON_GPIO GPIO_NUM_5
#define X_BUTTON_GPIO GPIO_NUM_9
#define Y_BUTTON_GPIO GPIO_NUM_4

#endif
```

`firmware/main/boards/scratch-arcade-s3/config.json`

```json
{
  "target": "esp32s3",
  "builds": [
    {
      "name": "scratch-arcade-s3",
      "sdkconfig_append": [
        "CONFIG_ESPTOOLPY_FLASHSIZE_8MB=y",
        "CONFIG_SPIRAM=y",
        "CONFIG_PARTITION_TABLE_CUSTOM_FILENAME=\"partitions/v2/8m.csv\"",
        "CONFIG_BOARD_TYPE_SCRATCH_ARCADE_S3=y"
      ]
    }
  ]
}
```

`firmware/main/boards/scratch-arcade-s3/README.md`

```md
# Scratch Arcade S3

Reference board source:
- `../arcade-lite/README.md`
- `../arcade-lite/firmware/README.md`

Known constraints:
- LCD/key pins come from `arcade-lite/firmware/README.md`
- The open-source Lite docs do not confirm a microphone input path
- Voice capture must stay disabled or guarded until hardware input is verified
```

Also add:
- `config BOARD_TYPE_SCRATCH_ARCADE_S3` to `firmware/main/Kconfig.projbuild`
- `elseif(CONFIG_BOARD_TYPE_SCRATCH_ARCADE_S3) set(BOARD_TYPE "scratch-arcade-s3")` to `firmware/main/CMakeLists.txt`

- [ ] **Step 4: Re-run the guard test and verify GREEN**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
python3 -m unittest tests/test_scratch_arcade_board_profile.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/jupiter/ave-xiaozhi
git add firmware/main/Kconfig.projbuild firmware/main/CMakeLists.txt firmware/main/boards/scratch-arcade-s3 firmware/tests/test_scratch_arcade_board_profile.py
git commit -m "feat: add scratch arcade s3 board profile"
```

### Task 2: Implement the Scratch Arcade board class and basic hardware bring-up

**Files:**
- Create: `firmware/main/boards/scratch-arcade-s3/scratch_arcade_s3_board.cc`
- Modify: `firmware/main/CMakeLists.txt`
- Test: `firmware/tests/test_scratch_arcade_board_profile.py`

- [ ] **Step 1: Extend the failing guard test to require the new board source**

Add:

```python
    def test_board_source_is_wired_into_main_build(self):
        cmake = (ROOT / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("boards/scratch-arcade-s3/scratch_arcade_s3_board.cc", cmake)
```

- [ ] **Step 2: Run the guard test and verify RED**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
python3 -m unittest tests/test_scratch_arcade_board_profile.py -v
```

Expected: FAIL because the board implementation file is not referenced yet.

- [ ] **Step 3: Implement the minimal board bring-up**

`firmware/main/boards/scratch-arcade-s3/scratch_arcade_s3_board.cc`

```cpp
#include "wifi_board.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "display/lcd_display.h"

#include <driver/spi_common.h>
#include <esp_lcd_panel_vendor.h>

extern "C" void ave_hw_key_press(int key);
extern "C" void ave_hw_listen_button(bool pressed);

class ScratchArcadeS3Board : public WifiBoard {
private:
    Button up_button_{DPAD_UP_BUTTON_GPIO};
    Button right_button_{DPAD_RIGHT_BUTTON_GPIO};
    Button down_button_{DPAD_DOWN_BUTTON_GPIO};
    Button left_button_{DPAD_LEFT_BUTTON_GPIO};
    Button fn_button_{FN_BUTTON_GPIO};
    Button a_button_{A_BUTTON_GPIO};
    Button b_button_{B_BUTTON_GPIO};
    Button x_button_{X_BUTTON_GPIO};
    Button y_button_{Y_BUTTON_GPIO};
    Display* display_ = nullptr;

    void InitializeSpi();
    void InitializeDisplay();
    void InitializeButtons();

public:
    ScratchArcadeS3Board();
    std::string GetBoardType() override { return "scratch-arcade-s3"; }
    Display* GetDisplay() override { return display_; }
    AudioCodec* GetAudioCodec() override { return nullptr; }
    void SetPowerSaveLevel(PowerSaveLevel level) override { WifiBoard::SetPowerSaveLevel(level); }
    std::string GetDeviceStatusJson() override { return WifiBoard::GetDeviceStatusJson(); }
};

DECLARE_BOARD(ScratchArcadeS3Board);
```

Implementation requirements:
- Initialize one SPI bus using the `arcade-lite` LCD pins.
- Create an ST7789 panel first; if the panel shows incorrect colors/orientation, adjust only `invert_color`, `swap_xy`, and `mirror`.
- Wire `left/right/up/down/a/b/x/y` single-clicks to `ave_hw_key_press(...)`.
- Wire `fn_button_` press-down/press-up to `ave_hw_listen_button(...)`.
- During startup, keep the existing `EnterWifiConfigMode()` behavior on `FN` click if the device is still in `kDeviceStateStarting`.

- [ ] **Step 4: Add the board source to the firmware build**

Add to `firmware/main/CMakeLists.txt`:

```cmake
list(APPEND SOURCES
    "boards/scratch-arcade-s3/scratch_arcade_s3_board.cc"
)
```

- [ ] **Step 5: Re-run the guard test and verify GREEN**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
python3 -m unittest tests/test_scratch_arcade_board_profile.py -v
```

Expected: PASS.

- [ ] **Step 6: Run a firmware compile smoke**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
idf.py set-target esp32s3
idf.py -DBOARD_NAME=scratch-arcade-s3 -DBOARD_TYPE=scratch-arcade-s3 build
```

Expected: build completes or fails only on the next missing AVE bridge symbols.

- [ ] **Step 7: Commit**

```bash
cd /home/jupiter/ave-xiaozhi
git add firmware/main/CMakeLists.txt firmware/main/boards/scratch-arcade-s3/scratch_arcade_s3_board.cc firmware/tests/test_scratch_arcade_board_profile.py
git commit -m "feat: add scratch arcade s3 board bring-up"
```

### Task 3: Add the AVE firmware bridge for display messages and hardware key transport

**Files:**
- Create: `firmware/main/ave/ave_hw_bridge.h`
- Create: `firmware/main/ave/ave_hw_bridge.cc`
- Create: `firmware/tests/test_ave_firmware_bridge.py`
- Modify: `firmware/main/CMakeLists.txt`
- Modify: `firmware/main/application.cc`
- Modify: `firmware/main/application.h`
- Modify: `firmware/main/protocols/protocol.h`
- Modify: `firmware/main/protocols/protocol.cc`

- [ ] **Step 1: Write the failing bridge guard test**

`firmware/tests/test_ave_firmware_bridge.py`

```python
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AveFirmwareBridgeTest(unittest.TestCase):
    def test_application_handles_display_messages(self):
        app = (ROOT / "main" / "application.cc").read_text(encoding="utf-8")
        self.assertIn('strcmp(type->valuestring, "display") == 0', app)
        self.assertIn("ave_hw_handle_display_json", app)

    def test_protocol_exposes_raw_json_send(self):
        protocol_h = (ROOT / "main" / "protocols" / "protocol.h").read_text(encoding="utf-8")
        protocol_cc = (ROOT / "main" / "protocols" / "protocol.cc").read_text(encoding="utf-8")
        self.assertIn("SendRawJson", protocol_h)
        self.assertIn("SendRawJson", protocol_cc)

    def test_bridge_is_compiled(self):
        cmake = (ROOT / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn('shared/ave_screens/ave_screen_manager.c', cmake)
        self.assertIn('main/ave/ave_hw_bridge.cc', cmake.replace('firmware/', ''))
```

- [ ] **Step 2: Run the bridge guard test and verify RED**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
python3 -m unittest tests/test_ave_firmware_bridge.py -v
```

Expected: FAIL because the AVE firmware bridge does not exist yet.

- [ ] **Step 3: Add the minimal bridge API**

`firmware/main/ave/ave_hw_bridge.h`

```cpp
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

void ave_hw_init(void* display);
void ave_hw_handle_display_json(const char* json);
void ave_hw_key_press(int key);
void ave_hw_listen_button(bool pressed);

#ifdef __cplusplus
}
#endif
```

`firmware/main/ave/ave_hw_bridge.cc`

```cpp
#include "ave_hw_bridge.h"
#include "application.h"
#include "ave_screen_manager.h"

void ave_hw_init(void* display) {
    ave_sm_init(static_cast<lv_display_t*>(display));
}

void ave_hw_handle_display_json(const char* json) {
    ave_sm_handle_json(json);
}

void ave_hw_key_press(int key) {
    ave_sm_key_press(key);
}

void ave_hw_listen_button(bool pressed) {
    auto& app = Application::GetInstance();
    if (pressed) app.StartListening();
    else app.StopListening();
}
```

Bridge requirements:
- Pull `shared/ave_screens/*.c` into the firmware build directly instead of `add_subdirectory(...)`.
- Do **not** compile `shared/ave_screens/ave_transport.c` into firmware; provide the hardware transport symbol from the bridge layer instead.
- Add a public `Protocol::SendRawJson(const std::string&)` wrapper that forwards to `SendText(...)`.
- Add `Application::SendRawJson(const std::string&)` and use it from the bridge implementation of `ave_send_json(...)`.

- [ ] **Step 4: Wire the runtime into `application.cc`**

Add:

```cpp
} else if (strcmp(type->valuestring, "display") == 0) {
    auto raw = cJSON_PrintUnformatted(root);
    Schedule([json = std::string(raw)]() {
        ave_hw_handle_display_json(json.c_str());
    });
    cJSON_free(raw);
```

And in `Initialize()` after display setup, initialize the AVE runtime:

```cpp
auto display = board.GetDisplay();
display->SetupUI();
ave_hw_init(lv_display_get_default());
```

- [ ] **Step 5: Re-run the bridge guard test and verify GREEN**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
python3 -m unittest tests/test_ave_firmware_bridge.py -v
```

Expected: PASS.

- [ ] **Step 6: Run focused regression and compile verification**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/simulator
./mock/run_screenshot_test.sh
```

Expected: PASS; shared AVE screens still behave the same after firmware-side bridge changes.

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
idf.py set-target esp32s3
idf.py -DBOARD_NAME=scratch-arcade-s3 -DBOARD_TYPE=scratch-arcade-s3 build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/jupiter/ave-xiaozhi
git add firmware/main/ave firmware/main/application.cc firmware/main/application.h firmware/main/protocols/protocol.h firmware/main/protocols/protocol.cc firmware/main/CMakeLists.txt firmware/tests/test_ave_firmware_bridge.py
git commit -m "feat: bridge ave screens into firmware"
```

### Task 4: Package, document, and validate the flashable target

**Files:**
- Modify: `server/docs/firmware-build.md`
- Modify: `docs/simulator-ui-guide.md`
- Modify: `docs/ave-feature-map.md`
- Modify: `firmware/main/boards/scratch-arcade-s3/README.md`

- [ ] **Step 1: Write the failing documentation guard**

Add to `firmware/tests/test_scratch_arcade_board_profile.py`:

```python
    def test_docs_reference_flashable_scratch_arcade_target(self):
        board_readme = (ROOT / "main" / "boards" / "scratch-arcade-s3" / "README.md").read_text(encoding="utf-8")
        self.assertIn("python scripts/release.py scratch-arcade-s3", board_readme)
        self.assertIn("merged-binary.bin", board_readme)
```

- [ ] **Step 2: Run the doc guard and verify RED**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
python3 -m unittest tests/test_scratch_arcade_board_profile.py -v
```

Expected: FAIL because the flashing instructions are not documented yet.

- [ ] **Step 3: Document the final flow**

Update `firmware/main/boards/scratch-arcade-s3/README.md` with:

```md
Build:
```bash
cd /home/jupiter/ave-xiaozhi/firmware
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
python scripts/release.py scratch-arcade-s3
```

Flash:
```bash
esptool.py --chip esp32s3 --port /dev/ttyACM0 write_flash -z 0 build/merged-binary.bin
```

Known limitation:
- Voice input stays blocked until the actual Scratch Arcade hardware variant is proven to expose a microphone path compatible with xiaozhi audio capture.
```

Also update:
- `server/docs/firmware-build.md` to mention `scratch-arcade-s3`
- `docs/simulator-ui-guide.md` to point to the new board target
- `docs/ave-feature-map.md` to say the board port exists once the build is validated

- [ ] **Step 4: Re-run the doc guard and verify GREEN**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
python3 -m unittest tests/test_scratch_arcade_board_profile.py -v
```

Expected: PASS.

- [ ] **Step 5: Produce the release artifact**

Run:

```bash
cd /home/jupiter/ave-xiaozhi/firmware
python scripts/release.py scratch-arcade-s3
```

Expected: `firmware/build/merged-binary.bin` and `firmware/releases/v<version>_scratch-arcade-s3.zip`.

- [ ] **Step 6: Hardware validation smoke**

Run on device:

```text
1. Flash `build/merged-binary.bin`
2. Confirm LCD boots in 320x240 landscape
3. Confirm d-pad and A/B/X/Y change AVE selection state
4. Confirm server-pushed `display` screens render on hardware
5. Confirm FN press behavior matches the verified hardware path:
   - with microphone: start/stop listening
   - without microphone: document unsupported voice input and keep non-voice navigation working
```

- [ ] **Step 7: Commit**

```bash
cd /home/jupiter/ave-xiaozhi
git add server/docs/firmware-build.md docs/simulator-ui-guide.md docs/ave-feature-map.md firmware/main/boards/scratch-arcade-s3/README.md firmware/tests/test_scratch_arcade_board_profile.py
git commit -m "docs: add scratch arcade s3 build and flash guide"
```
