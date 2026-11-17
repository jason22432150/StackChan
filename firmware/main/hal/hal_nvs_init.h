#pragma once

#include <nvs_flash.h>
#include <sdkconfig.h>

namespace hal_nvs {

inline esp_err_t initializeDefaultPartition()
{
    const auto result = nvs_flash_init();
#if !CONFIG_NVS_ENCRYPTION
    if (result == ESP_ERR_NVS_NO_FREE_PAGES || result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        const auto erase_result = nvs_flash_erase();
        return erase_result == ESP_OK ? nvs_flash_init() : erase_result;
    }
#endif
    // An encrypted build may encounter data written by another build. Leave
    // recovery to an explicit operator action so startup can't erase it.
    return result;
}

}  // namespace hal_nvs
