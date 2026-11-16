#include <cstdlib>
#include <iostream>
#include <string>
#include <stackchan/notifications/device_stream_json.h>

using namespace stackchan::notifications;

namespace {
constexpr std::size_t frame_limit = 1024;
constexpr auto generation = UINT64_MAX;

void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

std::string replaced(std::string text, std::string_view from, std::string_view to)
{
    const auto pos = text.find(from);
    expect(pos != std::string::npos, "test edit target exists");
    text.replace(pos, from.size(), to);
    return text;
}

const std::string heartbeat = R"({"schema_version":"0.1","message_id":"h","device_id":"dev","policy_version":"v1","generation":18446744073709551615,"direction":"coordinator_to_device","type":"heartbeat","sent_at":"1970-01-01T00:00:01.005Z"})";
const std::string intent = R"({"schema_version":"0.1","message_id":"i","device_id":"dev","policy_version":"v1","generation":18446744073709551615,"direction":"coordinator_to_device","type":"notification.intent","sent_at":"1970-01-01T00:00:01.006Z","delivery_id":"d","payload":{"schema_version":"0.1","notification_id":"n","delivery_id":"d","device_id":"dev","event_ids":["e"],"priority":100,"policy_version":"v1","generation":18446744073709551615,"expires_at":"1970-01-01T00:00:01.020Z","presentation_policy":{"ui":true,"audio":false,"motion":false,"tts":false}}})";

void verifyFrames(std::string_view heartbeat_frame, std::string_view intent_frame)
{
    NotificationController controller({1, 30, 5});
    DeviceStreamIngress ingress(controller, 10);
    expect(ingress.bindVerified({1, "dev", "v1", generation, 1050}, 1000, 0), "bind verified session");
    expect(receiveDeviceStreamJson(ingress, 1, heartbeat_frame, frame_limit, 5), "heartbeat activates");
    expect(receiveDeviceStreamJson(ingress, 1, intent_frame, frame_limit, 6), "intent reaches queue");
    const auto delivery = controller.takeNext(1, 6);
    expect(delivery && std::string_view(delivery->id.data()) == "d" && delivery->expires_at == 20,
           "delivery ID and exact converted deadline");
}

void testMalformedFrames()
{
    NotificationController controller({1, 30, 5});
    DeviceStreamIngress ingress(controller, 10);
    expect(ingress.bindVerified({1, "dev", "v1", generation, 1050}, 1000, 0), "bind verified session");
    for (const auto& bad : {
             heartbeat + "{}", heartbeat + " ", heartbeat.substr(0, heartbeat.size() - 1),
             replaced(heartbeat, R"("device_id":"dev")", R"("device_id":"other","device_id":"dev")"),
             replaced(heartbeat, "coordinator_to_device", "device_to_coordinator"),
             replaced(heartbeat, "18446744073709551615", "18446744073709551616"),
             replaced(heartbeat, "1970-01-01", "2026-02-29"),
             replaced(heartbeat, "dev", "de\xC0\xAF"),
         }) {
        expect(!receiveDeviceStreamJson(ingress, 1, bad, frame_limit, 5), "invalid heartbeat rejected");
    }
    expect(!receiveDeviceStreamJson(ingress, 1, heartbeat, heartbeat.size() - 1, 5), "byte limit enforced");
    expect(controller.state(5) == NotificationController::State::Recovering, "invalid frame cannot activate");
    expect(receiveDeviceStreamJson(ingress, 1, heartbeat, frame_limit, 5), "valid heartbeat activates");

    for (const auto& bad : {
             replaced(intent, R"("delivery_id":"d","payload")", R"("delivery_id":"other","payload")"),
             replaced(intent, R"("device_id":"dev","event_ids")", R"("device_id":"other","event_ids")"),
             replaced(intent, R"("e")", R"("e","e")"),
             replaced(intent, R"("ui":true)", R"("ui":1)"),
             replaced(intent, "01.020Z", "01.006Z"),
             replaced(intent, R"("priority":100)", R"("priority":101)"),
             replaced(intent, R"("notification_id":"n")", R"("unknown":"n")"),
         }) {
        expect(!receiveDeviceStreamJson(ingress, 1, bad, frame_limit, 6), "invalid intent rejected");
    }
    expect(!controller.takeNext(1, 6), "invalid intent cannot enqueue");
}
}  // namespace

int main(int argc, char**)
{
    if (argc == 2) {
        std::string encoded_heartbeat;
        std::string encoded_intent;
        expect(static_cast<bool>(std::getline(std::cin, encoded_heartbeat) && std::getline(std::cin, encoded_intent)),
               "expected two Coordinator-encoded frames");
        verifyFrames(encoded_heartbeat, encoded_intent);
    } else {
        verifyFrames(heartbeat, intent);
        testMalformedFrames();
    }
}
