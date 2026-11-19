#pragma once

#include <cstddef>
#include <cstdint>

using nvs_handle_t = std::uint32_t;
enum nvs_open_mode_t { NVS_READONLY, NVS_READWRITE };
inline constexpr int ESP_OK = 0;
inline constexpr int ESP_ERR_NVS_NOT_FOUND = 1;
inline constexpr int ESP_ERR_NVS_INVALID_LENGTH = 2;
inline constexpr int ESP_ERR_NVS_TYPE_MISMATCH = 3;

int nvs_open(const char* name, nvs_open_mode_t mode, nvs_handle_t* handle);
void nvs_close(nvs_handle_t handle);
int nvs_get_u16(nvs_handle_t handle, const char* key, std::uint16_t* out);
int nvs_get_u32(nvs_handle_t handle, const char* key, std::uint32_t* out);
int nvs_get_str(nvs_handle_t handle, const char* key, char* out, std::size_t* size);
int nvs_set_u16(nvs_handle_t handle, const char* key, std::uint16_t value);
int nvs_set_u32(nvs_handle_t handle, const char* key, std::uint32_t value);
int nvs_set_str(nvs_handle_t handle, const char* key, const char* value);
int nvs_commit(nvs_handle_t handle);
