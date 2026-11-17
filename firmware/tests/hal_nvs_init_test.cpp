#include <cstdlib>
#include <hal/hal_nvs_init.h>
#include <iostream>

namespace {
esp_err_t first_result = ESP_OK;
esp_err_t retry_result = ESP_OK;
esp_err_t erase_result = ESP_OK;
unsigned init_calls = 0;
unsigned erase_calls = 0;

void verify(esp_err_t first, esp_err_t expected, unsigned expected_init, unsigned expected_erase,
            esp_err_t erase = ESP_OK, esp_err_t retry = ESP_OK)
{
    first_result = first;
    retry_result = retry;
    erase_result = erase;
    init_calls = 0;
    erase_calls = 0;
    if (hal_nvs::initializeDefaultPartition() != expected ||
        init_calls != expected_init || erase_calls != expected_erase) {
        std::cerr << "unexpected NVS boot recovery for error " << first << '\n';
        std::exit(1);
    }
}
}  // namespace

esp_err_t nvs_flash_init()
{
    return ++init_calls == 1 ? first_result : retry_result;
}

esp_err_t nvs_flash_erase()
{
    ++erase_calls;
    return erase_result;
}

int main()
{
    verify(ESP_OK, ESP_OK, 1, 0);
    verify(ESP_FAIL, ESP_FAIL, 1, 0);
#if CONFIG_NVS_ENCRYPTION
    verify(ESP_ERR_NVS_NO_FREE_PAGES, ESP_ERR_NVS_NO_FREE_PAGES, 1, 0);
    verify(ESP_ERR_NVS_NEW_VERSION_FOUND, ESP_ERR_NVS_NEW_VERSION_FOUND, 1, 0);
#else
    verify(ESP_ERR_NVS_NO_FREE_PAGES, ESP_OK, 2, 1);
    verify(ESP_ERR_NVS_NEW_VERSION_FOUND, ESP_OK, 2, 1);
    verify(ESP_ERR_NVS_NO_FREE_PAGES, ESP_FAIL, 1, 1, ESP_FAIL);
    verify(ESP_ERR_NVS_NEW_VERSION_FOUND, ESP_FAIL, 2, 1, ESP_OK, ESP_FAIL);
#endif
}
