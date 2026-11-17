#pragma once

using BaseType_t = int;
using TickType_t = unsigned;
inline constexpr BaseType_t pdPASS = 1;
constexpr TickType_t pdMS_TO_TICKS(unsigned milliseconds) { return milliseconds / 10; }
