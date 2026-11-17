#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>

namespace stackchan::notifications {

/**
 * P2-07：裝置端 PresentationReceipt 狀態機與多次 ACK 冪等。
 *
 * 單一執行上下文。合法順序：accepted → started →（completed｜interrupted｜cancelled｜failed）。
 * 每個狀態產生獨立 receipt_id；相同 receipt_id 的重複轉移回傳 Duplicate。
 * Coordinator 對同一 receipt_id 的多次 ACK 視為一次成功（冪等）。
 * Generation 不符或已終態後不得再推進（過期 generation 不得復活呈現）。
 */
class PresentationReceiptTracker {
public:
    static constexpr std::size_t max_id_bytes = 128;
    static constexpr std::size_t max_reason_bytes = 128;
    static constexpr std::size_t max_ack_history = 8;

    using Generation = std::uint64_t;
    using UtcMs = std::uint64_t;

    enum class Status : std::uint8_t {
        None = 0,
        Accepted,
        Started,
        Completed,
        Interrupted,
        Cancelled,
        Failed,
    };

    enum class Outcome : std::uint8_t { Ok, Duplicate, Rejected };

    struct Receipt {
        std::array<char, max_id_bytes + 1> receipt_id{};
        std::array<char, max_id_bytes + 1> delivery_id{};
        std::array<char, max_id_bytes + 1> attempt_id{};
        std::array<char, max_id_bytes + 1> device_id{};
        Generation generation = 0;
        Status status = Status::None;
        std::array<char, max_reason_bytes + 1> reason{};
        bool has_reason = false;
        UtcMs reported_at_utc_ms = 0;
    };

    struct Result {
        Outcome outcome = Outcome::Rejected;
        std::optional<Receipt> receipt;
    };

    PresentationReceiptTracker() = default;

    Result accept(std::string_view receipt_id, std::string_view delivery_id, std::string_view attempt_id,
                  std::string_view device_id, Generation generation, UtcMs reported_at_utc_ms);
    Result start(std::string_view receipt_id, UtcMs reported_at_utc_ms);
    Result complete(std::string_view receipt_id, UtcMs reported_at_utc_ms);
    Result interrupt(std::string_view receipt_id, UtcMs reported_at_utc_ms, std::string_view reason = {});
    Result cancel(std::string_view receipt_id, UtcMs reported_at_utc_ms, std::string_view reason = {});
    Result fail(std::string_view receipt_id, UtcMs reported_at_utc_ms, std::string_view reason = {});

    /** Coordinator ACK：首次標記已確認；之後相同 receipt_id 回 Duplicate。未知 id 為 Rejected。 */
    Outcome acknowledge(std::string_view receipt_id);
    bool isAcknowledged(std::string_view receipt_id) const;

    Status status() const { return _status; }
    Generation generation() const { return _generation; }
    std::string_view deliveryId() const { return _delivery_id.data(); }

    static const char* statusText(Status status);

private:
    Result transition(Status next, std::string_view receipt_id, UtcMs reported_at_utc_ms,
                      std::string_view reason, bool require_started);
    bool rememberIssued(std::string_view receipt_id);
    bool wasIssued(std::string_view receipt_id) const;

    Status _status = Status::None;
    Generation _generation = 0;
    std::array<char, max_id_bytes + 1> _delivery_id{};
    std::array<char, max_id_bytes + 1> _attempt_id{};
    std::array<char, max_id_bytes + 1> _device_id{};
    std::array<std::array<char, max_id_bytes + 1>, max_ack_history> _issued{};
    std::array<bool, max_ack_history> _acked{};
    std::size_t _issued_count = 0;
};

/**
 * 將 Receipt 編碼為契約相容的 compact JSON（schema_version=0.1）。
 * 成功時寫入 out［0, *written），含結尾 '\\0' 於 out[*written]。
 */
bool encodePresentationReceiptJson(const PresentationReceiptTracker::Receipt& receipt, char* out,
                                   std::size_t capacity, std::size_t* written);

/** 將 UTC 毫秒編碼為 date-time（YYYY-MM-DDTHH:MM:SS.mmmZ）。 */
bool formatUtcDateTime(PresentationReceiptTracker::UtcMs utc_ms, char* out, std::size_t capacity);

}  // namespace stackchan::notifications
