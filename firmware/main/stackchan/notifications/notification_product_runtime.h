#pragma once

#include "stream_provision.h"

#include <cstdint>

namespace stackchan::notifications {

/**
 * P2-04 產品路徑。由專用通知任務初始化並持有 client。
 *
 * - 預設不開啟 TLS／WebSocket（無憑證絕不 connect）
 * - tick 必須在 LVGL lock 外呼叫
 * - Null UI：不掛 Avatar（P2-08）；仍經 LvglLockedUiPort 守鎖紀律
 * - 不呼叫 Xiaozhi Audio／Servo
 * - arm：僅接受已驗證 StreamProvision；init 本身不 fetch／不 start
 */
void initNotificationProductRuntime();

/**
 * 以已驗證 provision 武裝產品 runtime 的 DeviceStreamTlsClient。
 * Fail-Closed：未 init、已 started、profile 與 CoreS3 MVP 不符、或 provision／upgrade 無效 → false。
 */
bool armNotificationProductRuntime(const StreamProvision& provision);

/**
 * Explicitly load credentials and fetch policy before arming the product stream.
 * The caller supplies the Coordinator generation. Bootstrap stays idle until
 * the existing SNTP callback has confirmed synchronization in this boot.
 * TLS can block. Call outside the LVGL lock and serialize with runtime init,
 * arm and tick on the client owner context.
 */
bool fetchAndArmNotificationProductRuntime(std::uint64_t coordinator_generation);

/** 產品 stream 是否已 upgrade（client.started）。 */
bool isNotificationProductStreamArmed();

/** 專用通知任務每輪轉發 Xiaozhi Busy／Idle，並 poll 已啟用的 stream。 */
void tickNotificationProductRuntime(std::uint64_t now_ms, std::uint64_t utc_ms, bool xiaozhi_busy);

}  // namespace stackchan::notifications
