#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#include <stackchan/notifications/fail_closed_revoke_probe.h>

using stackchan::notifications::FailClosedRevokeProbe;
using stackchan::notifications::LvglLockHooks;
using stackchan::notifications::NoticeKind;
using stackchan::notifications::NotificationUiPort;
using stackchan::notifications::failClosedRevokeProbeLinked;
using stackchan::notifications::kMvpSoftWorstCaseRevokeMs;

namespace {
void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

struct FakeUi final : NotificationUiPort {
    std::vector<std::string> ops;
    bool show(NoticeKind, std::string_view text) override
    {
        ops.push_back(std::string("show:") + std::string(text));
        return true;
    }
    void clear() override { ops.push_back("clear"); }
};

void lockFn(void*) {}
void unlockFn(void*) {}

void testWorstCasePollSkewWithinBudget()
{
    FakeUi ui;
    // heartbeat 50ms、stability 5ms，加速 host 模擬。
    FailClosedRevokeProbe probe{ui, LvglLockHooks{lockFn, unlockFn, nullptr}, {4, 50, 5}, 50 + 185};
    std::uint64_t now = 0;
    bool got = false;
    for (int i = 0; i < 500 && !got; ++i) {
        got = probe.poll(now);
        // 模擬 update task：20ms 節奏，最壞再疊加一次 gap。
        now += (i == 10) ? 185 : 20;
    }
    expect(got && probe.sample().has_value(), "sample produced");
    const auto& s = *probe.sample();
    expect(s.interrupted, "interrupted");
    expect(s.within_budget, "within budget");
    expect(s.revoke_ms >= 50, "at least heartbeat timeout");
    expect(s.revoke_ms <= s.budget_ms, "revoke_ms <= budget");
    expect(!ui.ops.empty() && ui.ops.back() == "clear", "ui cleared");
}

void testLinkedProbe()
{
    expect(failClosedRevokeProbeLinked(), "link probe");
    expect(kMvpSoftWorstCaseRevokeMs == 4185, "budget constant");
}
}  // namespace

int main()
{
    testLinkedProbe();
    testWorstCasePollSkewWithinBudget();
}
