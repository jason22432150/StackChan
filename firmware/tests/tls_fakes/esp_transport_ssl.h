#pragma once
#include "esp_transport.h"
esp_transport_handle_t esp_transport_ssl_init();
void esp_transport_ssl_set_cert_data(esp_transport_handle_t, const char*, int);
