#include <array>
#include <cstdio>

#include <esp_adc/adc_oneshot.h>
#include <esp_lcd_panel_vendor.h>
#include <esp_log.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "application.h"
#include "audio/codecs/no_audio_codec.h"
#include "ave_screen_manager.h"
#include "board.h"
#include "button.h"
#include "display/lcd_display.h"
#include "wifi_board.h"

#include "config.h"
#include "joystick_axis.h"

#define TAG "ScratchArcade"

class ScratchArcade : public WifiBoard {
private:
    static constexpr TickType_t kJoystickPollInterval = pdMS_TO_TICKS(30);
    static constexpr int kJoystickCalibrationSamples = 4;
    static constexpr int kJoystickCalibrationMaxDelta = 450;

    struct JoystickAxis {
        const char* name;
        gpio_num_t gpio;
        adc_channel_t channel;
        int center;
        scratch_arcade::AxisDirection direction = scratch_arcade::AxisDirection::kCenter;
        int last_raw = -1;
    };

    Button boot_button_;
    Button dpad_left_button_;
    Button dpad_right_button_;
    Button dpad_up_button_;
    Button dpad_down_button_;
    Button x_button_;
    Button y_button_;
    Button a_button_;
    Button b_button_;
    LcdDisplay* display_ = nullptr;
    TaskHandle_t joystick_task_handle_ = nullptr;
    adc_oneshot_unit_handle_t adc1_handle_ = nullptr;
    std::array<JoystickAxis, 2> joystick_axes_ = {{
        {"horizontal", JOYSTICK_HORIZONTAL_GPIO, JOYSTICK_HORIZONTAL_ADC_CHANNEL,
         JOYSTICK_HORIZONTAL_ADC_CENTER},
        {"vertical", JOYSTICK_VERTICAL_GPIO, JOYSTICK_VERTICAL_ADC_CHANNEL,
         JOYSTICK_VERTICAL_ADC_CENTER},
    }};

    static void JoystickTaskEntry(void* arg) {
        static_cast<ScratchArcade*>(arg)->RunJoystickTask();
    }

    static int AbsInt(int value) {
        return value < 0 ? -value : value;
    }

    void InitializeSpi() {
        spi_bus_config_t buscfg = {};
        buscfg.mosi_io_num = DISPLAY_MOSI_PIN;
        buscfg.miso_io_num = GPIO_NUM_NC;
        buscfg.sclk_io_num = DISPLAY_CLK_PIN;
        buscfg.quadwp_io_num = GPIO_NUM_NC;
        buscfg.quadhd_io_num = GPIO_NUM_NC;
        buscfg.max_transfer_sz = DISPLAY_WIDTH * DISPLAY_HEIGHT * sizeof(uint16_t);
        ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &buscfg, SPI_DMA_CH_AUTO));
    }

    void InitializeLcdDisplay() {
        esp_lcd_panel_io_handle_t panel_io = nullptr;
        esp_lcd_panel_handle_t panel = nullptr;

        esp_lcd_panel_io_spi_config_t io_config = {};
        io_config.cs_gpio_num = DISPLAY_CS_PIN;
        io_config.dc_gpio_num = DISPLAY_DC_PIN;
        io_config.spi_mode = DISPLAY_SPI_MODE;
        io_config.pclk_hz = 40 * 1000 * 1000;
        io_config.trans_queue_depth = 10;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(SPI2_HOST, &io_config, &panel_io));

        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = DISPLAY_RST_PIN;
        panel_config.rgb_ele_order = DISPLAY_RGB_ORDER;
        panel_config.bits_per_pixel = 16;
        ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(panel_io, &panel_config, &panel));

        esp_lcd_panel_reset(panel);
        esp_lcd_panel_init(panel);
        esp_lcd_panel_invert_color(panel, DISPLAY_INVERT_COLOR);
        esp_lcd_panel_swap_xy(panel, DISPLAY_SWAP_XY);
        esp_lcd_panel_mirror(panel, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y);

        display_ = new SpiLcdDisplay(panel_io, panel, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                     DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X,
                                     DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY);
    }

    void DispatchAveKey(int key, const char* name) {
        auto& app = Application::GetInstance();
        app.Schedule([key, name]() {
            auto& app = Application::GetInstance();
            auto state = app.GetDeviceState();
            if (state == kDeviceStateStarting || state == kDeviceStateWifiConfiguring) {
                ESP_LOGI(TAG, "AVE key press ignored during state=%d: %s (%d)",
                         static_cast<int>(state), name, key);
                return;
            }
            auto display = Board::GetInstance().GetDisplay();
            if (display == nullptr) {
                ESP_LOGW(TAG, "AVE key press dropped: display missing");
                return;
            }
            DisplayLockGuard lock(display);
            ESP_LOGI(TAG, "AVE key press: %s (%d)", name, key);
            ave_sm_key_press(key);
        });
    }

    void BindAveKey(Button& button, int key, const char* name) {
        button.OnPressDown([this, key, name]() { DispatchAveKey(key, name); });
    }

    bool ReadJoystickAxis(JoystickAxis& axis, int* out_raw) {
        if (adc1_handle_ == nullptr) {
            return false;
        }
        esp_err_t ret = adc_oneshot_read(adc1_handle_, axis.channel, out_raw);
        if (ret != ESP_OK) {
            ESP_LOGW(TAG, "JOYSTICK read failed axis=%s gpio=%d err=%s", axis.name,
                     static_cast<int>(axis.gpio), esp_err_to_name(ret));
            return false;
        }
        axis.last_raw = *out_raw;
        return true;
    }

    void CalibrateJoystickCenters() {
        for (auto& axis : joystick_axes_) {
            int total = 0;
            int count = 0;
            for (int i = 0; i < kJoystickCalibrationSamples; ++i) {
                int raw = 0;
                if (ReadJoystickAxis(axis, &raw)) {
                    total += raw;
                    ++count;
                }
                vTaskDelay(pdMS_TO_TICKS(5));
            }
            if (count == 0) {
                ESP_LOGW(TAG, "JOYSTICK calibration skipped axis=%s center=%d", axis.name,
                         axis.center);
                continue;
            }
            const int average = total / count;
            if (AbsInt(average - axis.center) <= kJoystickCalibrationMaxDelta) {
                axis.center = average;
            }
            axis.last_raw = average;
            ESP_LOGI(TAG,
                     "JOYSTICK axis=%s gpio=%d center=%d sampled=%d press_delta=%d release_delta=%d",
                     axis.name, static_cast<int>(axis.gpio), axis.center, average,
                     JOYSTICK_ADC_PRESS_DELTA, JOYSTICK_ADC_RELEASE_DELTA);
        }
    }

    void InitializeJoystick() {
        adc_oneshot_unit_init_cfg_t init_cfg = {
            .unit_id = ADC_UNIT_1,
            .ulp_mode = ADC_ULP_MODE_DISABLE,
        };
        ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_cfg, &adc1_handle_));

        adc_oneshot_chan_cfg_t chan_cfg = {
            .atten = ADC_ATTEN_DB_12,
            .bitwidth = ADC_BITWIDTH_DEFAULT,
        };
        for (const auto& axis : joystick_axes_) {
            ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle_, axis.channel, &chan_cfg));
        }
        CalibrateJoystickCenters();

        BaseType_t task_ret = xTaskCreate(JoystickTaskEntry, "scratch_joy", 4096, this, 2,
                                          &joystick_task_handle_);
        ESP_LOGI(TAG, "JOYSTICK task create ret=%ld handle=%p", static_cast<long>(task_ret),
                 joystick_task_handle_);
    }

    void HandleJoystickAxis(JoystickAxis& axis, int positive_key, const char* positive_name,
                            int negative_key, const char* negative_name) {
        int raw = 0;
        if (!ReadJoystickAxis(axis, &raw)) {
            return;
        }

        const scratch_arcade::AxisThresholds thresholds = {
            .center = axis.center,
            .press_delta = JOYSTICK_ADC_PRESS_DELTA,
            .release_delta = JOYSTICK_ADC_RELEASE_DELTA,
        };
        const auto next_direction =
            scratch_arcade::DecideAxisDirection(raw, axis.direction, thresholds);
        if (next_direction == axis.direction) {
            return;
        }

        axis.direction = next_direction;
        if (next_direction == scratch_arcade::AxisDirection::kPositive) {
            ESP_LOGI(TAG, "JOYSTICK axis=%s raw=%d -> %s", axis.name, raw, positive_name);
            DispatchAveKey(positive_key, positive_name);
            return;
        }
        if (next_direction == scratch_arcade::AxisDirection::kNegative) {
            ESP_LOGI(TAG, "JOYSTICK axis=%s raw=%d -> %s", axis.name, raw, negative_name);
            DispatchAveKey(negative_key, negative_name);
            return;
        }
        ESP_LOGD(TAG, "JOYSTICK axis=%s raw=%d -> center", axis.name, raw);
    }

    void RunJoystickTask() {
        ESP_LOGI(TAG, "JOYSTICK task started");
        while (true) {
            HandleJoystickAxis(joystick_axes_[0], AVE_KEY_LEFT, "left", AVE_KEY_RIGHT,
                               "right");
            HandleJoystickAxis(joystick_axes_[1], AVE_KEY_UP, "up", AVE_KEY_DOWN, "down");
            vTaskDelay(kJoystickPollInterval);
        }
    }

    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting ||
                app.GetDeviceState() == kDeviceStateWifiConfiguring) {
                EnterWifiConfigMode();
            }
        });

        boot_button_.OnPressDown([]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting) {
                return;
            }
            ESP_LOGI(TAG, "PTT start (state=%d)", static_cast<int>(app.GetDeviceState()));
            app.StartListening();
        });
        boot_button_.OnPressUp([]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting) {
                return;
            }
            ESP_LOGI(TAG, "PTT stop (state=%d)", static_cast<int>(app.GetDeviceState()));
            app.StopListening();
        });

        BindAveKey(dpad_left_button_, AVE_KEY_LEFT, "left");
        BindAveKey(dpad_right_button_, AVE_KEY_RIGHT, "right");
        BindAveKey(dpad_up_button_, AVE_KEY_UP, "up");
        BindAveKey(dpad_down_button_, AVE_KEY_DOWN, "down");
        BindAveKey(x_button_, AVE_KEY_X, "x");
        BindAveKey(y_button_, AVE_KEY_Y, "y");
        BindAveKey(a_button_, AVE_KEY_A, "a");
        BindAveKey(b_button_, AVE_KEY_B, "b");
    }

public:
    ScratchArcade()
        : boot_button_(BOOT_BUTTON_GPIO),
          dpad_left_button_(DPAD_LEFT_BUTTON_GPIO),
          dpad_right_button_(DPAD_RIGHT_BUTTON_GPIO),
          dpad_up_button_(DPAD_UP_BUTTON_GPIO),
          dpad_down_button_(DPAD_DOWN_BUTTON_GPIO),
          x_button_(BUTTON_X_GPIO),
          y_button_(BUTTON_Y_GPIO),
          a_button_(BUTTON_A_GPIO),
          b_button_(BUTTON_B_GPIO) {
        InitializeSpi();
        InitializeLcdDisplay();
        InitializeButtons();
        InitializeJoystick();
        GetBacklight()->RestoreBrightness();
    }

    AudioCodec* GetAudioCodec() override {
        static NoAudioCodecSimplexPdm audio_codec(AUDIO_INPUT_SAMPLE_RATE,
                                                  AUDIO_OUTPUT_SAMPLE_RATE,
                                                  AUDIO_I2S_SPK_GPIO_BCLK,
                                                  AUDIO_I2S_SPK_GPIO_LRCK,
                                                  AUDIO_I2S_SPK_GPIO_DOUT,
                                                  I2S_STD_SLOT_BOTH,
                                                  AUDIO_I2S_MIC_GPIO_SCK,
                                                  AUDIO_I2S_MIC_GPIO_DIN);
        return &audio_codec;
    }

    Display* GetDisplay() override { return display_; }

    Backlight* GetBacklight() override {
        static PwmBacklight backlight(DISPLAY_BACKLIGHT_PIN, DISPLAY_BACKLIGHT_OUTPUT_INVERT);
        return &backlight;
    }
};

DECLARE_BOARD(ScratchArcade);
