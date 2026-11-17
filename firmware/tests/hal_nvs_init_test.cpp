#include <cstdlib>
#include <cstring>
#include <hal/hal_nvs_init.h>
#include <iostream>

namespace {
esp_err_t first_result = ESP_OK;
esp_err_t retry_result = ESP_OK;
esp_err_t erase_result = ESP_OK;
unsigned init_calls = 0;
unsigned erase_calls = 0;

#if CONFIG_NVS_ENCRYPTION
nvs_sec_scheme_t scheme;
esp_err_t read_result = ESP_OK;
esp_err_t secure_result = ESP_OK;
unsigned read_calls = 0;
unsigned secure_calls = 0;
unsigned zeroize_calls = 0;
constexpr unsigned char key_byte = 0x5a;

void verifyEncrypted(esp_err_t read, esp_err_t secure, esp_err_t expected, unsigned expected_secure_calls)
{
    read_result = read;
    secure_result = secure;
    read_calls = secure_calls = zeroize_calls = 0;
    if (hal_nvs::initializeDefaultPartition() != expected || read_calls != 1 ||
        secure_calls != expected_secure_calls || zeroize_calls != 1 || init_calls != 0 || erase_calls != 0) {
        std::cerr << "unexpected encrypted NVS initialization for read result " << read << '\n';
        std::exit(1);
    }
}
#else
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
#endif
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

#if CONFIG_NVS_ENCRYPTION
nvs_sec_scheme_t* nvs_flash_get_default_security_scheme()
{
    return &scheme;
}

esp_err_t nvs_flash_read_security_cfg_v2(nvs_sec_scheme_t* provider, nvs_sec_cfg_t* config)
{
    if (provider != &scheme || config == nullptr) {
        std::exit(1);
    }
    ++read_calls;
    // A provider can leave key material in the buffer even on failure.
    std::memset(config, key_byte, sizeof(*config));
    return read_result;
}

esp_err_t nvs_flash_secure_init(nvs_sec_cfg_t* config)
{
    if (config == nullptr || config->eky[0] != key_byte || config->tky[0] != key_byte) {
        std::exit(1);
    }
    ++secure_calls;
    return secure_result;
}

void mbedtls_platform_zeroize(void* buffer, std::size_t size)
{
    if (buffer == nullptr || size != sizeof(nvs_sec_cfg_t) ||
        *static_cast<const unsigned char*>(buffer) != key_byte) {
        std::exit(1);
    }
    ++zeroize_calls;
    std::memset(buffer, 0, size);
}
#endif

int main()
{
#if CONFIG_NVS_ENCRYPTION
    verifyEncrypted(ESP_OK, ESP_OK, ESP_OK, 1);
    verifyEncrypted(ESP_ERR_NVS_KEYS_NOT_INITIALIZED, ESP_OK, ESP_ERR_NVS_KEYS_NOT_INITIALIZED, 0);
    verifyEncrypted(ESP_ERR_NVS_CORRUPT_KEY_PART, ESP_OK, ESP_ERR_NVS_CORRUPT_KEY_PART, 0);
    verifyEncrypted(ESP_FAIL, ESP_OK, ESP_FAIL, 0);
    verifyEncrypted(ESP_OK, ESP_ERR_NVS_NO_FREE_PAGES, ESP_ERR_NVS_NO_FREE_PAGES, 1);
    verifyEncrypted(ESP_OK, ESP_ERR_NVS_NEW_VERSION_FOUND, ESP_ERR_NVS_NEW_VERSION_FOUND, 1);
#else
    verify(ESP_OK, ESP_OK, 1, 0);
    verify(ESP_FAIL, ESP_FAIL, 1, 0);
    verify(ESP_ERR_NVS_NO_FREE_PAGES, ESP_OK, 2, 1);
    verify(ESP_ERR_NVS_NEW_VERSION_FOUND, ESP_OK, 2, 1);
    verify(ESP_ERR_NVS_NO_FREE_PAGES, ESP_FAIL, 1, 1, ESP_FAIL);
    verify(ESP_ERR_NVS_NEW_VERSION_FOUND, ESP_FAIL, 2, 1, ESP_OK, ESP_FAIL);
#endif
}
