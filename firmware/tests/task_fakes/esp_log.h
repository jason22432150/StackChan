#pragma once

#include <cstddef>

void ESP_LOGI(const char* tag, const char* format, const char* phase, unsigned stack,
              std::size_t free, std::size_t minimum, std::size_t largest, const char* result);
