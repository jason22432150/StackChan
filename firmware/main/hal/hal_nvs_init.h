#pragma once

#include <nvs_flash.h>
#include <sdkconfig.h>

#if CONFIG_NVS_ENCRYPTION
#include <mbedtls/platform_util.h>
#endif

namespace hal_nvs {

inline esp_err_t initializeDefaultPartition()
{
#if CONFIG_NVS_ENCRYPTION
    // nvs_flash_init() generates keys when the configured provider cannot read them.
    nvs_sec_cfg_t config{};
    const auto read_result = nvs_flash_read_security_cfg_v2(nvs_flash_get_default_security_scheme(), &config);
    const auto result = read_result == ESP_OK ? nvs_flash_secure_init(&config) : read_result;
    mbedtls_platform_zeroize(&config, sizeof(config));
    return result;
#else
    const auto result = nvs_flash_init();
    if (result == ESP_ERR_NVS_NO_FREE_PAGES || result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        const auto erase_result = nvs_flash_erase();
        return erase_result == ESP_OK ? nvs_flash_init() : erase_result;
    }
    return result;
#endif
}

}  // namespace hal_nvs
