#pragma once

#include "personal_pending_ingress.h"

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace stackchan::notifications {

/**
 * 解析 Pi `GET .../notifications/pending` 回傳 JSON，並餵入 PersonalPendingIngress。
 *
 * 期望形狀：`{"items":[...],"count":N}`；每筆至少含 device_id／policy_version／generation／
 * delivery_id／expires_at。呼叫端須先 `pulse` 維持 Active。
 * 回傳成功 enqueue 筆數；根契約失敗回傳 0。
 */
std::size_t applyPersonalPendingJson(PersonalPendingIngress& ingress, std::string_view json,
                                     std::size_t max_bytes, PersonalPendingIngress::Tick now);

/**
 * 自已通過根契約的 pending JSON 收集 delivery_id（供 ACK）。
 * 根契約失敗回傳 0；最多寫入 max_ids 筆。
 */
std::size_t collectPersonalPendingDeliveryIds(std::string_view json, std::size_t max_bytes,
                                              std::vector<std::string>& out, std::size_t max_ids = 8);

}  // namespace stackchan::notifications
