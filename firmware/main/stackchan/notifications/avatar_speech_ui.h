#pragma once

#include "notification_presenter.h"

#include <string_view>

namespace stackchan::notifications {

/**
 * Avatar／speech bubble 通知埠（可注入 sink，便於 host 測試）。
 * 實際 LVGL 更新仍須由外層 LvglLockedUiPort 持鎖後呼叫。
 */
struct AvatarSpeechSink {
    bool (*show)(void* ctx, NoticeKind kind, std::string_view text) = nullptr;
    void (*clear)(void* ctx) = nullptr;
    void* ctx = nullptr;

    bool valid() const { return show != nullptr && clear != nullptr; }
};

class AvatarSpeechUi final : public NotificationUiPort {
public:
    explicit AvatarSpeechUi(AvatarSpeechSink sink);

    bool show(NoticeKind kind, std::string_view text) override;
    void clear() override;

private:
    AvatarSpeechSink _sink;
};

/** 裝置端：綁定 GetStackChan().avatar() speech／emotion。 */
AvatarSpeechSink makeDeviceAvatarSpeechSink();

}  // namespace stackchan::notifications
