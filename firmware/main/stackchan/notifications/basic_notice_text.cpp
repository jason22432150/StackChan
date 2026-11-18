#include "basic_notice_text.h"

#include <cstring>

namespace stackchan::notifications {
namespace {

constexpr std::string_view kNeutralLabel = "Agent update";
constexpr std::string_view kSuccessLabel = "Agent done";

bool appendView(char* out, std::size_t out_bytes, std::size_t& used, std::string_view part)
{
    if (part.empty()) {
        return true;
    }
    if (used >= out_bytes || out_bytes - used <= part.size()) {
        return false;
    }
    std::memcpy(out + used, part.data(), part.size());
    used += part.size();
    return true;
}

}  // namespace

bool isBasicNoticeTextSafe(std::string_view text)
{
    if (text.empty() || text.size() > NotificationPresenter::max_text_bytes ||
        text.find('\0') != std::string_view::npos) {
        return false;
    }
    for (unsigned char c : text) {
        if (c < 0x20 || c == '"' || c == '\\') {
            return false;
        }
    }
    return true;
}

std::size_t formatBasicNoticeText(NoticeKind kind, std::string_view delivery_id, char* out,
                                  std::size_t out_bytes)
{
    if (out == nullptr || out_bytes == 0) {
        return 0;
    }
    out[0] = '\0';
    const auto label = kind == NoticeKind::Success ? kSuccessLabel : kNeutralLabel;
    std::size_t used = 0;
    if (!appendView(out, out_bytes, used, label)) {
        out[0] = '\0';
        return 0;
    }

    // 可選附上短 delivery 尾碼，方便對帳；截斷並過濾不安全字元。
    if (!delivery_id.empty()) {
        constexpr std::size_t max_id_suffix = 24;
        char suffix[max_id_suffix + 1] = {};
        std::size_t suffix_len = 0;
        for (char c : delivery_id) {
            if (suffix_len >= max_id_suffix) {
                break;
            }
            const auto uc = static_cast<unsigned char>(c);
            if (uc < 0x20 || uc == '"' || uc == '\\' || c == '\0') {
                continue;
            }
            suffix[suffix_len++] = c;
        }
        if (suffix_len > 0) {
            if (!appendView(out, out_bytes, used, ": ") ||
                !appendView(out, out_bytes, used, std::string_view(suffix, suffix_len))) {
                // 空間不足時退回純標籤。
                used = label.size();
            }
        }
    }

    if (used >= out_bytes) {
        out[0] = '\0';
        return 0;
    }
    out[used] = '\0';
    const std::string_view result(out, used);
    if (!isBasicNoticeTextSafe(result)) {
        out[0] = '\0';
        return 0;
    }
    return used;
}

}  // namespace stackchan::notifications
