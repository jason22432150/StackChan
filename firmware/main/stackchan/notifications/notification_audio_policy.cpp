#include "notification_audio_policy.h"

namespace stackchan::notifications {

NotificationAudioGate::NotificationAudioGate(AgentAudioCapability capability) : _capability(capability) {}

bool NotificationAudioGate::authorize(bool policy_audio, bool policy_tts) const
{
    if (policy_tts) {
        return allowsTts();
    }
    if (policy_audio) {
        return allowsCue();
    }
    // 政策未要求音訊：視為純 UI，允許（由 Presenter 處理畫面）。
    return true;
}

bool NotificationAudioGate::tryAcquireAudioLease(ResourceArbiter& arbiter,
                                                 ResourceArbiter::Generation generation,
                                                 ResourceArbiter::Tick now) const
{
    if (!allowsCue()) {
        // A0：明確不碰 Audio 租約，避免誤開播放路徑。
        return false;
    }
    return arbiter.tryAcquire(generation, ResourceArbiter::Resource::Audio, now);
}

bool NotificationAudioGate::playCue(PlayFn play, void* ctx) const
{
    if (!allowsCue() || play == nullptr) {
        return false;
    }
    return play(ctx);
}

bool NotificationAudioGate::playTts(PlayFn play, void* ctx) const
{
    if (!allowsTts() || play == nullptr) {
        return false;
    }
    return play(ctx);
}

bool mvpAgentAudioIsA0()
{
    return kMvpAgentAudioCapability == AgentAudioCapability::A0;
}

}  // namespace stackchan::notifications
