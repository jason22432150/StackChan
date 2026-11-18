#include "avatar_speech_ui.h"

#include "basic_notice_text.h"

#include <stackchan/avatar/avatar/elements/emotion.h>
#include <stackchan/stackchan.h>

namespace stackchan::notifications {
namespace {

bool deviceShow(void* /*ctx*/, NoticeKind kind, std::string_view text)
{
    if (!isBasicNoticeTextSafe(text)) {
        return false;
    }
    auto& stackchan = GetStackChan();
    if (!stackchan.hasAvatar()) {
        return false;
    }
    auto& avatar = stackchan.avatar();
    if (kind == NoticeKind::Success) {
        avatar.setEmotion(stackchan::avatar::Emotion::Happy);
    } else {
        avatar.setEmotion(stackchan::avatar::Emotion::Neutral);
    }
    avatar.setSpeech(text);
    return true;
}

void deviceClear(void* /*ctx*/)
{
    auto& stackchan = GetStackChan();
    if (!stackchan.hasAvatar()) {
        return;
    }
    auto& avatar = stackchan.avatar();
    avatar.clearSpeech();
    avatar.setEmotion(stackchan::avatar::Emotion::Neutral);
}

}  // namespace

AvatarSpeechSink makeDeviceAvatarSpeechSink()
{
    return AvatarSpeechSink{deviceShow, deviceClear, nullptr};
}

}  // namespace stackchan::notifications
