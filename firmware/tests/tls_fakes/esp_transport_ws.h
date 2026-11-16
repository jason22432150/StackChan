#pragma once
#include "esp_transport.h"
enum { WS_TRANSPORT_OPCODES_TEXT = 1, WS_TRANSPORT_OPCODES_CLOSE = 8 };
struct esp_transport_ws_config_t {
    const char* ws_path;
    const char* headers;
};
esp_transport_handle_t esp_transport_ws_init(esp_transport_handle_t);
int esp_transport_ws_set_config(esp_transport_handle_t, const esp_transport_ws_config_t*);
int esp_transport_ws_get_upgrade_request_status(esp_transport_handle_t);
int esp_transport_ws_get_read_opcode(esp_transport_handle_t);
int esp_transport_ws_get_read_payload_len(esp_transport_handle_t);
bool esp_transport_ws_get_fin_flag(esp_transport_handle_t);
