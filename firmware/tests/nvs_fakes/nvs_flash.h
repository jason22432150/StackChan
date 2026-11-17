#pragma once

#include "nvs.h"

using esp_err_t = int;
inline constexpr esp_err_t ESP_FAIL = -1;
inline constexpr esp_err_t ESP_ERR_NVS_NO_FREE_PAGES = 4;
inline constexpr esp_err_t ESP_ERR_NVS_NEW_VERSION_FOUND = 5;
inline constexpr esp_err_t ESP_ERR_NVS_KEYS_NOT_INITIALIZED = 6;
inline constexpr esp_err_t ESP_ERR_NVS_CORRUPT_KEY_PART = 7;

struct nvs_sec_scheme_t {};
struct nvs_sec_cfg_t {
    unsigned char eky[32];
    unsigned char tky[32];
};

esp_err_t nvs_flash_init();
esp_err_t nvs_flash_erase();
nvs_sec_scheme_t* nvs_flash_get_default_security_scheme();
esp_err_t nvs_flash_read_security_cfg_v2(nvs_sec_scheme_t* scheme, nvs_sec_cfg_t* config);
esp_err_t nvs_flash_secure_init(nvs_sec_cfg_t* config);
