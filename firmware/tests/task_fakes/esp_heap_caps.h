#pragma once

#include <cstddef>

inline constexpr unsigned MALLOC_CAP_INTERNAL = 1;
inline constexpr unsigned MALLOC_CAP_8BIT = 2;
std::size_t heap_caps_get_free_size(unsigned caps);
std::size_t heap_caps_get_minimum_free_size(unsigned caps);
std::size_t heap_caps_get_largest_free_block(unsigned caps);
