#include <cstdlib>
#include <iostream>
#include <optional>
#include <string>
#include <vector>
#include <stackchan/notifications/personal_pending_http_client.h>
#include <stackchan/notifications/personal_pending_json.h>
#include <stackchan/notifications/personal_pending_poll.h>

using stackchan::notifications::PersonalPendingHttpClient;
using stackchan::notifications::personalPendingFetchDue;
using stackchan::notifications::personalPendingPollOnce;

namespace {
bool armed = true;
unsigned feeds = 0;
unsigned ticks = 0;
unsigned fetches = 0;
unsigned acks = 0;
unsigned collect_calls = 0;
std::optional<std::string> fetch_body = std::string(R"({"items":[],"count":0})");
bool fetch_ok = true;
std::size_t feed_return = 0;

void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}
}  // namespace

namespace stackchan::notifications {
bool isPersonalPendingNotificationArmed() { return armed; }
std::size_t feedPersonalPendingNotificationJson(std::string_view body, std::uint64_t, std::uint64_t)
{
    ++feeds;
    expect(!body.empty(), "feed receives body");
    return feed_return;
}
void tickNotificationProductRuntime(std::uint64_t, std::uint64_t, bool) { ++ticks; }

std::size_t collectPersonalPendingDeliveryIds(std::string_view, std::size_t, std::vector<std::string>& out,
                                              std::size_t max_ids)
{
    ++collect_calls;
    out.clear();
    if (max_ids == 0) {
        return 0;
    }
    out.emplace_back("dlv_stub_1");
    return out.size();
}

std::optional<PersonalPendingHttpClient::Result> PersonalPendingHttpClient::fetch(const Config&)
{
    ++fetches;
    if (!fetch_ok) {
        return std::nullopt;
    }
    return Result{*fetch_body};
}

bool PersonalPendingHttpClient::ack(const Config&, std::string_view delivery_id)
{
    ++acks;
    expect(delivery_id == "dlv_stub_1", "ack delivery id");
    return true;
}
}  // namespace stackchan::notifications

int main()
{
    expect(personalPendingFetchDue(0, 100, 5000), "first fetch due");
    expect(!personalPendingFetchDue(100, 100, 5000), "same instant not due");
    expect(!personalPendingFetchDue(100, 5099, 5000), "before interval");
    expect(personalPendingFetchDue(100, 5100, 5000), "after interval");
    expect(!personalPendingFetchDue(0, 100, 0), "zero interval never due");

    PersonalPendingHttpClient client;
    PersonalPendingHttpClient::Config http{"192.168.20.148", 8443, "", "tok", "cores3_primary"};
    std::uint64_t last = 0;
    armed = true;
    feed_return = 0;
    expect(personalPendingPollOnce(last, 5000, http, client, 100, 1000, false), "armed after poll");
    expect(fetches == 1 && feeds == 1 && ticks == 1 && last == 100 && acks == 0 && collect_calls == 0,
           "first cycle fetch+feed+tick no ack when fed=0");

    expect(personalPendingPollOnce(last, 5000, http, client, 120, 1020, false), "within interval");
    expect(fetches == 1 && feeds == 1 && ticks == 2, "no refetch before interval");

    // Xiaozhi busy：跳過 fetch，不推進 last_fetch，仍 tick
    expect(personalPendingPollOnce(last, 5000, http, client, 5200, 5200, true), "busy still ticks");
    expect(fetches == 1 && feeds == 1 && ticks == 3 && last == 100, "busy skips fetch");

    fetch_ok = false;
    expect(personalPendingPollOnce(last, 5000, http, client, 5200, 5200, false), "failed fetch still ticks");
    expect(fetches == 2 && feeds == 1 && ticks == 4 && last == 5200, "failed fetch advances last");

    fetch_ok = true;
    feed_return = 1;
    expect(personalPendingPollOnce(last, 5000, http, client, 10200, 10200, false), "fed triggers ack");
    expect(fetches == 3 && feeds == 2 && ticks == 5 && collect_calls == 1 && acks == 1,
           "ack after successful feed+tick");

    armed = false;
    expect(!personalPendingPollOnce(last, 5000, http, client, 15300, 15300, false), "disarmed stops");
    expect(fetches == 3 && ticks == 5, "disarmed skips work");
}
