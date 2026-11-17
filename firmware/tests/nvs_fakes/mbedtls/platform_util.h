#pragma once

#include <cstddef>

void mbedtls_platform_zeroize(void* buffer, std::size_t size);
