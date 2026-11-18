#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <string_view>

#include <stackchan/notifications/basic_notice_text.h>

using stackchan::notifications::NoticeKind;
using stackchan::notifications::formatBasicNoticeText;
using stackchan::notifications::isBasicNoticeTextSafe;

namespace {

void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

void testNeutralWithDelivery()
{
    char buf[129] = {};
    const auto n = formatBasicNoticeText(NoticeKind::Neutral, "dlv-1", buf, sizeof(buf));
    expect(n > 0, "format ok");
    expect(std::string_view(buf, n) == "Agent update: dlv-1", "neutral label + id");
    expect(isBasicNoticeTextSafe(buf), "safe");
}

void testSuccessLabelOnlyStyle()
{
    char buf[129] = {};
    const auto n = formatBasicNoticeText(NoticeKind::Success, "ok-9", buf, sizeof(buf));
    expect(n > 0, "format ok");
    // Success 僅樣式標籤，不宣稱 task.succeeded。
    expect(std::string_view(buf, n) == "Agent done: ok-9", "success style label");
}

void testRejectsUnsafeControlChars()
{
    expect(!isBasicNoticeTextSafe("bad\"x"), "quote unsafe");
    expect(!isBasicNoticeTextSafe("bad\\x"), "backslash unsafe");
    expect(!isBasicNoticeTextSafe(""), "empty unsafe");
}

void testTruncatesLongDelivery()
{
    char buf[129] = {};
    const std::string long_id(64, 'a');
    const auto n = formatBasicNoticeText(NoticeKind::Neutral, long_id, buf, sizeof(buf));
    expect(n > 0, "format ok");
    expect(std::string_view(buf, n).find("Agent update: ") == 0, "prefix");
    expect(std::strlen(buf) <= 128, "within presenter limit");
    expect(isBasicNoticeTextSafe(buf), "still safe");
}

void testNullBufferFailsClosed()
{
    expect(formatBasicNoticeText(NoticeKind::Neutral, "x", nullptr, 16) == 0, "null out");
}

}  // namespace

int main()
{
    testNeutralWithDelivery();
    testSuccessLabelOnlyStyle();
    testRejectsUnsafeControlChars();
    testTruncatesLongDelivery();
    testNullBufferFailsClosed();
    return 0;
}
