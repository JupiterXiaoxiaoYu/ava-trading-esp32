#include <esp_log.h>
#include <esp_err.h>
#include <nvs.h>
#include <nvs_flash.h>
#include <driver/gpio.h>
#include <esp_event.h>
#if CONFIG_ESP_TASK_WDT_EN
#include <esp_task_wdt.h>
#endif
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "application.h"

#define TAG "main"

extern "C" void app_main(void)
{
    // Initialize NVS flash for WiFi configuration
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "Erasing NVS flash to fix corruption");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

#if CONFIG_BOARD_TYPE_SCRATCH_ARCADE && CONFIG_ESP_TASK_WDT_EN
    // Probe firmware should stay alive long enough to collect evidence even if
    // some startup path starves idle tasks temporarily.
    esp_err_t wdt_ret = esp_task_wdt_deinit();
    ESP_LOGW(TAG, "Scratch Arcade probe build: esp_task_wdt_deinit -> %s", esp_err_to_name(wdt_ret));
#endif

    // Initialize and run the application
    auto& app = Application::GetInstance();
    app.Initialize();
    ESP_LOGI(TAG, "Application initialized, entering main loop");
    app.Run();  // This function runs the main event loop and never returns
}
