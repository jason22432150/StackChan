#include "presentation_receipt.h"

#include <algorithm>
#include <cstdio>
#include <cstring>

namespace stackchan::notifications {
namespace {

bool jsonSafeText(std::string_view text)
{
    // Fail-Closed：拒絕需 JSON 跳脫的字元，避免 snprintf 組字破壞契約。
    for (unsigned char c : text) {
        if (c < 0x20 || c == '"' || c == '\\') {
            return false;
        }
    }
    return true;
}

bool validIdentifier(std::string_view id, std::size_t max_bytes)
{
    return !id.empty() && id.size() <= max_bytes && id.find('\0') == std::string_view::npos &&
           jsonSafeText(id);
}

void copyId(std::array<char, PresentationReceiptTracker::max_id_bytes + 1>& dest, std::string_view id)
{
    dest.fill('\0');
    std::copy(id.begin(), id.end(), dest.begin());
}

bool sameId(const std::array<char, PresentationReceiptTracker::max_id_bytes + 1>& stored,
            std::string_view id)
{
    return std::string_view(stored.data()) == id;
}

bool isTerminal(PresentationReceiptTracker::Status status)
{
    using Status = PresentationReceiptTracker::Status;
    return status == Status::Completed || status == Status::Interrupted || status == Status::Cancelled ||
           status == Status::Failed;
}

}  // namespace

const char* PresentationReceiptTracker::statusText(Status status)
{
    switch (status) {
        case Status::Accepted:
            return "accepted";
        case Status::Started:
            return "started";
        case Status::Completed:
            return "completed";
        case Status::Interrupted:
            return "interrupted";
        case Status::Cancelled:
            return "cancelled";
        case Status::Failed:
            return "failed";
        case Status::None:
            break;
    }
    return "";
}

bool PresentationReceiptTracker::wasIssued(std::string_view receipt_id) const
{
    for (std::size_t i = 0; i < _issued_count; ++i) {
        if (sameId(_issued[i], receipt_id)) {
            return true;
        }
    }
    return false;
}

bool PresentationReceiptTracker::rememberIssued(std::string_view receipt_id)
{
    if (wasIssued(receipt_id)) {
        return false;
    }
    if (_issued_count >= max_ack_history) {
        // 環形覆蓋最舊紀錄，保持有界 RAM（MVP 單次呈現足夠）。
        for (std::size_t i = 1; i < max_ack_history; ++i) {
            _issued[i - 1] = _issued[i];
            _acked[i - 1] = _acked[i];
        }
        _issued_count = max_ack_history - 1;
    }
    copyId(_issued[_issued_count], receipt_id);
    _acked[_issued_count] = false;
    ++_issued_count;
    return true;
}

PresentationReceiptTracker::Result PresentationReceiptTracker::accept(
    std::string_view receipt_id, std::string_view delivery_id, std::string_view attempt_id,
    std::string_view device_id, Generation generation, UtcMs reported_at_utc_ms)
{
    if (!validIdentifier(receipt_id, max_id_bytes) || !validIdentifier(delivery_id, max_id_bytes) ||
        !validIdentifier(attempt_id, max_id_bytes) || !validIdentifier(device_id, max_id_bytes) ||
        generation == 0) {
        return {Outcome::Rejected, std::nullopt};
    }
    if (wasIssued(receipt_id)) {
        return {Outcome::Duplicate, std::nullopt};
    }
    if (_status != Status::None && !isTerminal(_status)) {
        return {Outcome::Rejected, std::nullopt};
    }

    _status = Status::Accepted;
    _generation = generation;
    copyId(_delivery_id, delivery_id);
    copyId(_attempt_id, attempt_id);
    copyId(_device_id, device_id);
    rememberIssued(receipt_id);

    Receipt receipt;
    copyId(receipt.receipt_id, receipt_id);
    copyId(receipt.delivery_id, delivery_id);
    copyId(receipt.attempt_id, attempt_id);
    copyId(receipt.device_id, device_id);
    receipt.generation = generation;
    receipt.status = Status::Accepted;
    receipt.reported_at_utc_ms = reported_at_utc_ms;
    return {Outcome::Ok, receipt};
}

PresentationReceiptTracker::Result PresentationReceiptTracker::transition(
    Status next, std::string_view receipt_id, UtcMs reported_at_utc_ms, std::string_view reason,
    bool require_started)
{
    if (!validIdentifier(receipt_id, max_id_bytes)) {
        return {Outcome::Rejected, std::nullopt};
    }
    if (wasIssued(receipt_id)) {
        return {Outcome::Duplicate, std::nullopt};
    }
    if (_status == Status::None || isTerminal(_status) || _generation == 0) {
        return {Outcome::Rejected, std::nullopt};
    }
    if (require_started) {
        if (_status != Status::Started) {
            return {Outcome::Rejected, std::nullopt};
        }
    } else if (next == Status::Started) {
        if (_status != Status::Accepted) {
            return {Outcome::Rejected, std::nullopt};
        }
    } else {
        // interrupt／cancel／fail：Accepted 或 Started 皆可（搶占可能在 started 前）。
        if (_status != Status::Accepted && _status != Status::Started) {
            return {Outcome::Rejected, std::nullopt};
        }
    }
    if (reason.size() > max_reason_bytes || reason.find('\0') != std::string_view::npos ||
        !jsonSafeText(reason)) {
        return {Outcome::Rejected, std::nullopt};
    }

    rememberIssued(receipt_id);
    _status = next;

    Receipt receipt;
    copyId(receipt.receipt_id, receipt_id);
    copyId(receipt.delivery_id, _delivery_id.data());
    copyId(receipt.attempt_id, _attempt_id.data());
    copyId(receipt.device_id, _device_id.data());
    receipt.generation = _generation;
    receipt.status = next;
    receipt.reported_at_utc_ms = reported_at_utc_ms;
    if (!reason.empty()) {
        receipt.reason.fill('\0');
        std::copy(reason.begin(), reason.end(), receipt.reason.begin());
        receipt.has_reason = true;
    }
    return {Outcome::Ok, receipt};
}

PresentationReceiptTracker::Result PresentationReceiptTracker::start(std::string_view receipt_id,
                                                                     UtcMs reported_at_utc_ms)
{
    return transition(Status::Started, receipt_id, reported_at_utc_ms, {}, false);
}

PresentationReceiptTracker::Result PresentationReceiptTracker::complete(std::string_view receipt_id,
                                                                        UtcMs reported_at_utc_ms)
{
    return transition(Status::Completed, receipt_id, reported_at_utc_ms, {}, true);
}

PresentationReceiptTracker::Result PresentationReceiptTracker::interrupt(std::string_view receipt_id,
                                                                         UtcMs reported_at_utc_ms,
                                                                         std::string_view reason)
{
    return transition(Status::Interrupted, receipt_id, reported_at_utc_ms, reason, false);
}

PresentationReceiptTracker::Result PresentationReceiptTracker::cancel(std::string_view receipt_id,
                                                                      UtcMs reported_at_utc_ms,
                                                                      std::string_view reason)
{
    return transition(Status::Cancelled, receipt_id, reported_at_utc_ms, reason, false);
}

PresentationReceiptTracker::Result PresentationReceiptTracker::fail(std::string_view receipt_id,
                                                                    UtcMs reported_at_utc_ms,
                                                                    std::string_view reason)
{
    return transition(Status::Failed, receipt_id, reported_at_utc_ms, reason, false);
}

PresentationReceiptTracker::Outcome PresentationReceiptTracker::acknowledge(std::string_view receipt_id)
{
    if (!validIdentifier(receipt_id, max_id_bytes)) {
        return Outcome::Rejected;
    }
    for (std::size_t i = 0; i < _issued_count; ++i) {
        if (sameId(_issued[i], receipt_id)) {
            if (_acked[i]) {
                return Outcome::Duplicate;
            }
            _acked[i] = true;
            return Outcome::Ok;
        }
    }
    return Outcome::Rejected;
}

bool PresentationReceiptTracker::isAcknowledged(std::string_view receipt_id) const
{
    for (std::size_t i = 0; i < _issued_count; ++i) {
        if (sameId(_issued[i], receipt_id)) {
            return _acked[i];
        }
    }
    return false;
}

bool formatUtcDateTime(PresentationReceiptTracker::UtcMs utc_ms, char* out, std::size_t capacity)
{
    if (out == nullptr || capacity < 25) {
        return false;
    }
    const auto secs = static_cast<std::int64_t>(utc_ms / 1000);
    const auto millis = static_cast<unsigned>(utc_ms % 1000);
    // 民用格里高利曆（1970 起）；足夠契約 date-time，不含 leap second。
    std::int64_t days = secs / 86400;
    std::int64_t tod = secs % 86400;
    if (tod < 0) {
        tod += 86400;
        --days;
    }
    const int hour = static_cast<int>(tod / 3600);
    const int minute = static_cast<int>((tod % 3600) / 60);
    const int second = static_cast<int>(tod % 60);

    std::int64_t z = days + 719468;
    const std::int64_t era = (z >= 0 ? z : z - 146096) / 146097;
    const unsigned doe = static_cast<unsigned>(z - era * 146097);
    const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    std::int64_t year = static_cast<std::int64_t>(yoe) + era * 400;
    const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const unsigned mp = (5 * doy + 2) / 153;
    const unsigned day = doy - (153 * mp + 2) / 5 + 1;
    const unsigned month = mp < 10 ? mp + 3 : mp - 9;
    year += (month <= 2);

    const int written =
        std::snprintf(out, capacity, "%04lld-%02u-%02uT%02d:%02d:%02d.%03uZ",
                      static_cast<long long>(year), month, day, hour, minute, second, millis);
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

bool encodePresentationReceiptJson(const PresentationReceiptTracker::Receipt& receipt, char* out,
                                   std::size_t capacity, std::size_t* written)
{
    if (out == nullptr || written == nullptr || capacity < 2) {
        return false;
    }
    const char* status = PresentationReceiptTracker::statusText(receipt.status);
    if (status[0] == '\0' || receipt.generation == 0) {
        return false;
    }
    char reported_at[32];
    if (!formatUtcDateTime(receipt.reported_at_utc_ms, reported_at, sizeof(reported_at))) {
        return false;
    }

    // compact JSON；欄位順序固定以利測試對照契約。
    int n = 0;
    if (receipt.has_reason) {
        n = std::snprintf(
            out, capacity,
            "{\"schema_version\":\"0.1\",\"receipt_id\":\"%s\",\"delivery_id\":\"%s\","
            "\"attempt_id\":\"%s\",\"device_id\":\"%s\",\"generation\":%llu,\"status\":\"%s\","
            "\"reason\":\"%s\",\"reported_at\":\"%s\"}",
            receipt.receipt_id.data(), receipt.delivery_id.data(), receipt.attempt_id.data(),
            receipt.device_id.data(), static_cast<unsigned long long>(receipt.generation), status,
            receipt.reason.data(), reported_at);
    } else {
        n = std::snprintf(
            out, capacity,
            "{\"schema_version\":\"0.1\",\"receipt_id\":\"%s\",\"delivery_id\":\"%s\","
            "\"attempt_id\":\"%s\",\"device_id\":\"%s\",\"generation\":%llu,\"status\":\"%s\","
            "\"reported_at\":\"%s\"}",
            receipt.receipt_id.data(), receipt.delivery_id.data(), receipt.attempt_id.data(),
            receipt.device_id.data(), static_cast<unsigned long long>(receipt.generation), status,
            reported_at);
    }
    if (n <= 0 || static_cast<std::size_t>(n) >= capacity) {
        return false;
    }
    *written = static_cast<std::size_t>(n);
    return true;
}

}  // namespace stackchan::notifications
