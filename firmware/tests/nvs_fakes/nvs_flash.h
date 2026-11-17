#pragma once

#include "nvs.h"

using esp_err_t = int;
inline constexpr esp_err_t ESP_FAIL = -1;
inline constexpr esp_err_t ESP_ERR_NVS_NO_FREE_PAGES = 4;
inline constexpr esp_err_t ESP_ERR_NVS_NEW_VERSION_FOUND = 5;

esp_err_t nvs_flash_init();
esp_err_t nvs_flash_erase();
