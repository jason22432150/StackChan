#pragma once

#include "FreeRTOS.h"

using TaskFunction_t = void (*)(void*);
using TaskHandle_t = void*;
BaseType_t xTaskCreate(TaskFunction_t entry, const char* name, unsigned stack_bytes, void* argument,
                       unsigned priority, TaskHandle_t* task);
void vTaskDelay(TickType_t ticks);
void vTaskDelete(TaskHandle_t task);
unsigned uxTaskGetStackHighWaterMark(TaskHandle_t task);
