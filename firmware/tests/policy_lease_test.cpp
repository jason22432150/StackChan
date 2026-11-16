#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <stackchan/notifications/policy_lease.h>

using stackchan::notifications::PolicyLeaseBinding;
using stackchan::notifications::bindPolicyLease;
using stackchan::notifications::parsePolicyLeaseJson;

namespace {
constexpr std::size_t limit = 256;
// 2026-11-16T12:00:00.000Z
constexpr auto now_ms = 1'794'830'400'000ULL;

void expect(bool passed, const char* message)
{
    if (!passed) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

std::string replaced(std::string text, std::string_view from, std::string_view to)
{
    const auto pos = text.find(from);
    expect(pos != std::string::npos, "edit target exists");
    text.replace(pos, from.size(), to);
    return text;
}
}  // namespace

int main()
{
    const std::string valid =
        R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2026-11-17T12:00:00Z"})";
    const auto lease = parsePolicyLeaseJson(valid, limit, now_ms);
    expect(lease.has_value(), "valid OpenAPI Policy parses");
    expect(std::string_view(lease->policy_id.data()) == "desk", "policy_id retained");
    expect(std::string_view(lease->version.data()) == "v1", "version retained");
    expect(std::string_view(lease->privacy_mode.data()) == "private", "privacy_mode retained");
    expect(lease->expires_utc_ms == 1'794'916'800'000ULL, "valid_until without millis converts");

    PolicyLeaseBinding bound{};
    expect(bindPolicyLease(bound, *lease, now_ms), "fresh lease can bind");
    expect(std::strcmp(bound.version.data(), "v1") == 0 && bound.expires_utc_ms == lease->expires_utc_ms,
           "bind copies stream fields");
    expect(!bindPolicyLease(bound, *lease, lease->expires_utc_ms), "expired lease cannot rebind");

    const std::string with_millis =
        R"({"policy_id":"desk","version":"v1","privacy_mode":"strict","valid_until":"2026-11-17T12:00:00.500Z"})";
    const auto millis_lease = parsePolicyLeaseJson(with_millis, limit, now_ms);
    expect(millis_lease && millis_lease->expires_utc_ms == 1'794'916'800'500ULL,
           "millisecond valid_until is accepted");

    const std::string revoked_false =
        R"({"policy_id":"desk","version":"v1","privacy_mode":"public","valid_until":"2026-11-17T12:00:00Z","revoked":false})";
    expect(parsePolicyLeaseJson(revoked_false, limit, now_ms).has_value(), "revoked:false is allowed");

    for (const auto& bad : {
             valid + " ",
             replaced(valid, "private", "shared"),
             replaced(valid, "2026-11-17T12:00:00Z", "2026-11-16T11:00:00Z"),
             replaced(valid, R"("valid_until":"2026-11-17T12:00:00Z")",
                      R"("valid_until":"2026-11-17T12:00:00Z","revoked":true)"),
             replaced(valid, R"("policy_id":"desk")", R"("policy_id":"desk","extra":1)"),
             replaced(valid, "desk", "bad id"),
             std::string(R"({"policy_id":"desk","version":"v1","privacy_mode":"private"})"),
         }) {
        expect(!parsePolicyLeaseJson(bad, limit, now_ms), "invalid policy lease rejected");
    }
    expect(!parsePolicyLeaseJson(valid, valid.size() - 1, now_ms), "byte limit enforced");
    expect(!parsePolicyLeaseJson(valid, limit, 0), "unsynchronized clock fails closed");
}
