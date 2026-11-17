#include <cstdlib>
#include <iostream>
#include <stackchan/notifications/notification_audio_policy.h>
#include <stackchan/notifications/resource_arbiter.h>

using stackchan::notifications::AgentAudioCapability;
using stackchan::notifications::NotificationAudioGate;
using stackchan::notifications::ResourceArbiter;
using stackchan::notifications::kMvpAgentAudioCapability;
using stackchan::notifications::mvpAgentAudioIsA0;

namespace {
void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

int play_calls = 0;
bool playSink(void*)
{
    ++play_calls;
    return true;
}

void testMvpLockedToA0()
{
    expect(kMvpAgentAudioCapability == AgentAudioCapability::A0, "MVP capability is A0");
    expect(mvpAgentAudioIsA0(), "mvpAgentAudioIsA0");
    NotificationAudioGate gate;
    expect(!gate.allowsCue() && !gate.allowsTts(), "A0 denies cue and tts");
}

void testA0RejectsPolicyAudioAndTts()
{
    NotificationAudioGate gate(AgentAudioCapability::A0);
    expect(gate.authorize(false, false), "pure UI policy ok");
    expect(!gate.authorize(true, false), "A0 rejects audio cue policy");
    expect(!gate.authorize(false, true), "A0 rejects tts policy");
    expect(!gate.authorize(true, true), "A0 rejects both");
}

void testA0NeverCallsPlaySinkOrAcquiresAudioLease()
{
    play_calls = 0;
    NotificationAudioGate gate(AgentAudioCapability::A0);
    ResourceArbiter arbiter;
    const auto gen = arbiter.beginPresentation(1);
    expect(arbiter.tryAcquire(gen, ResourceArbiter::Resource::Ui, 1), "ui still allowed");
    expect(!gate.tryAcquireAudioLease(arbiter, gen, 1), "A0 blocks audio lease");
    expect(!arbiter.hasLease(ResourceArbiter::Resource::Audio), "no audio lease held");
    expect(!gate.playCue(playSink, nullptr), "cue blocked");
    expect(!gate.playTts(playSink, nullptr), "tts blocked");
    expect(play_calls == 0, "play sink never invoked under A0");
}

void testHigherCapabilityWouldAllowButIsNotMvpDefault()
{
    // 證明閘門語意，非啟用 A1／A2。
    NotificationAudioGate a1(AgentAudioCapability::A1);
    expect(a1.allowsCue() && !a1.allowsTts(), "A1 cue only");
    expect(a1.authorize(true, false), "A1 allows cue policy");
    expect(!a1.authorize(false, true), "A1 rejects tts");

    play_calls = 0;
    expect(a1.playCue(playSink, nullptr) && play_calls == 1, "A1 can play cue in unit test only");
    expect(!a1.playTts(playSink, nullptr) && play_calls == 1, "A1 still blocks tts");

    NotificationAudioGate a2(AgentAudioCapability::A2);
    expect(a2.allowsTts() && a2.authorize(true, true), "A2 allows tts policy");
    expect(mvpAgentAudioIsA0(), "MVP remains A0 despite local higher-gate probes");
}
}  // namespace

int main()
{
    testMvpLockedToA0();
    testA0RejectsPolicyAudioAndTts();
    testA0NeverCallsPlaySinkOrAcquiresAudioLease();
    testHigherCapabilityWouldAllowButIsNotMvpDefault();
    return 0;
}
