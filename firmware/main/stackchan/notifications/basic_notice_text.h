#pragma once

#include "notification_presenter.h"

#include <cstddef>
#include <string_view>

namespace stackchan::notifications {

/**
 * 個人版基本提示文案（不含 Prompt／機密、不宣稱未經證實的 task.succeeded）。
 *
 * NoticeKind::Success 只代表成功樣式，呼叫端必須已有來源成功證據才可選用。
 * 回傳寫入字元數（不含 NUL）；失敗回 0。
 */
std::size_t formatBasicNoticeText(NoticeKind kind, std::string_view delivery_id, char* out,
                                  std::size_t out_bytes);

/** 文案是否可安全交給 Presenter／speech bubble（長度、控制字元）。 */
bool isBasicNoticeTextSafe(std::string_view text);

}  // namespace stackchan::notifications
