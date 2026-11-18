#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#include <stackchan/notifications/avatar_speech_ui.h>
#include <stackchan/notifications/basic_notice_text.h>

using stackchan::notifications::AvatarSpeechSink;
using stackchan::notifications::AvatarSpeechUi;
using stackchan::notifications::NoticeKind;

namespace {

void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

struct Capture {
    std::vector<std::string> ops;
    NoticeKind last_kind = NoticeKind::Neutral;
};

bool captureShow(void* ctx, NoticeKind kind, std::string_view text)
{
    auto* cap = static_cast<Capture*>(ctx);
    cap->last_kind = kind;
    cap->ops.push_back(std::string("show:") + std::string(text));
    return true;
}

void captureClear(void* ctx)
{
    static_cast<Capture*>(ctx)->ops.push_back("clear");
}

void testShowAndClear()
{
    Capture cap;
    AvatarSpeechUi ui{AvatarSpeechSink{captureShow, captureClear, &cap}};
    expect(ui.show(NoticeKind::Neutral, "Agent update: a1"), "show ok");
    expect(cap.ops.size() == 1 && cap.ops[0] == "show:Agent update: a1", "recorded show");
    expect(cap.last_kind == NoticeKind::Neutral, "kind");
    ui.clear();
    expect(cap.ops.size() == 2 && cap.ops.back() == "clear", "recorded clear");
}

void testRejectsUnsafeText()
{
    Capture cap;
    AvatarSpeechUi ui{AvatarSpeechSink{captureShow, captureClear, &cap}};
    expect(!ui.show(NoticeKind::Neutral, "bad\"quote"), "reject quote");
    expect(cap.ops.empty(), "no show");
}

void testInvalidSinkFailsClosed()
{
    AvatarSpeechUi ui{AvatarSpeechSink{}};
    expect(!ui.show(NoticeKind::Neutral, "Agent update"), "invalid sink");
    ui.clear();  // no-op
}

}  // namespace

int main()
{
    testShowAndClear();
    testRejectsUnsafeText();
    testInvalidSinkFailsClosed();
    return 0;
}
