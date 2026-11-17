#pragma once

#include "resource_arbiter.h"

#include <cstdint>

namespace stackchan::notifications {

/**
 * P0-03／P2-09：Agent 通知音訊能力等級。
 * - A0：無 Agent 通知音訊（純 UI）
 * - A1：短提示音（尚未驗證，不得啟用）
 * - A2：文字 TTS（尚未驗證，不得啟用）
 */
enum class AgentAudioCapability : std::uint8_t { A0 = 0, A1 = 1, A2 = 2 };

/** MVP 凍結能力：維持 A0，直到 A1／A2 實機 Gate 通過並經授權升級。 */
inline constexpr AgentAudioCapability kMvpAgentAudioCapability = AgentAudioCapability::A0;

/**
 * P2-09：通知音訊授權閘門。
 *
 * A0 下永遠拒絕 cue／TTS，且不得取得 ResourceArbiter::Audio 租約。
 * 本模組不 include／呼叫 Application::PlaySound、AudioCodec 或 Xiaozhi TTS。
 */
class NotificationAudioGate {
public:
    explicit NotificationAudioGate(AgentAudioCapability capability = kMvpAgentAudioCapability);

    AgentAudioCapability capability() const { return _capability; }
    bool allowsCue() const { return _capability >= AgentAudioCapability::A1; }
    bool allowsTts() const { return _capability >= AgentAudioCapability::A2; }

    /**
     * 依 presentation_policy 的 audio／tts 旗標與能力等級授權。
     * A0：兩者皆拒。A1：僅 audio cue。A2：audio＋tts。
     */
    bool authorize(bool policy_audio, bool policy_tts) const;

    /**
     * 嘗試取得通知 Audio 租約。A0 一律失敗且不呼叫 tryAcquire(Audio)。
     * 較高等級仍須通過 arbiter／Xiaozhi Busy 規則。
     */
    bool tryAcquireAudioLease(ResourceArbiter& arbiter, ResourceArbiter::Generation generation,
                              ResourceArbiter::Tick now) const;

    /** 播放短提示／TTS 的唯一入口；A0／未授權時回 false 且不執行 sink。 */
    using PlayFn = bool (*)(void* ctx);
    bool playCue(PlayFn play, void* ctx) const;
    bool playTts(PlayFn play, void* ctx) const;

private:
    AgentAudioCapability _capability;
};

/** link_anchor／測試：回傳目前 MVP 是否鎖定 A0。 */
bool mvpAgentAudioIsA0();

}  // namespace stackchan::notifications
