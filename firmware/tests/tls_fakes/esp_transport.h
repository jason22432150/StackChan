#pragma once
struct TestTransport;
using esp_transport_handle_t = TestTransport*;
inline constexpr int ESP_OK = 0;
int esp_transport_connect(esp_transport_handle_t, const char*, int, int);
int esp_transport_read(esp_transport_handle_t, char*, int, int);
int esp_transport_close(esp_transport_handle_t);
int esp_transport_destroy(esp_transport_handle_t);
