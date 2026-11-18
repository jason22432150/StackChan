#include "avatar_speech_ui.h"

#include "basic_notice_text.h"

namespace stackchan::notifications {

AvatarSpeechUi::AvatarSpeechUi(AvatarSpeechSink sink) : _sink(sink) {}

bool AvatarSpeechUi::show(NoticeKind kind, std::string_view text)
{
    if (!_sink.valid() || !isBasicNoticeTextSafe(text)) {
        return false;
    }
    return _sink.show(_sink.ctx, kind, text);
}

void AvatarSpeechUi::clear()
{
    if (!_sink.valid()) {
        return;
    }
    _sink.clear(_sink.ctx);
}

}  // namespace stackchan::notifications
