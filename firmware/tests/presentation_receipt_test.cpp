#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <stackchan/notifications/presentation_receipt.h>

using stackchan::notifications::PresentationReceiptTracker;
using stackchan::notifications::encodePresentationReceiptJson;
using stackchan::notifications::formatUtcDateTime;
using Outcome = PresentationReceiptTracker::Outcome;
using Status = PresentationReceiptTracker::Status;

namespace {
void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

void testHappyPathAcceptedStartedCompleted()
{
    PresentationReceiptTracker tracker;
    const auto accepted =
        tracker.accept("rcp-a", "dlv-1", "att-1", "cores3", 1, 1'000);
    expect(accepted.outcome == Outcome::Ok && accepted.receipt.has_value(), "accept ok");
    expect(tracker.status() == Status::Accepted, "accepted state");

    const auto started = tracker.start("rcp-s", 1'100);
    expect(started.outcome == Outcome::Ok, "start ok");
    expect(tracker.status() == Status::Started, "started state");

    const auto completed = tracker.complete("rcp-c", 1'200);
    expect(completed.outcome == Outcome::Ok, "complete ok");
    expect(tracker.status() == Status::Completed, "completed terminal");
    expect(tracker.complete("rcp-c2", 1'300).outcome == Outcome::Rejected, "terminal blocks complete");
}

void testInterruptFromStartedAndIdempotentAck()
{
    PresentationReceiptTracker tracker;
    expect(tracker.accept("rcp-a", "dlv-1", "att-1", "cores3", 2, 2'000).outcome == Outcome::Ok,
           "accept");
    expect(tracker.start("rcp-s", 2'100).outcome == Outcome::Ok, "start");
    const auto interrupted = tracker.interrupt("rcp-i", 2'200, "xiaozhi.busy");
    expect(interrupted.outcome == Outcome::Ok && interrupted.receipt->has_reason, "interrupt with reason");
    expect(tracker.status() == Status::Interrupted, "interrupted");

    expect(tracker.acknowledge("rcp-a") == Outcome::Ok, "first ack");
    expect(tracker.acknowledge("rcp-a") == Outcome::Duplicate, "duplicate ack idempotent");
    expect(tracker.isAcknowledged("rcp-a"), "acked flag");
    expect(tracker.acknowledge("rcp-s") == Outcome::Ok, "ack start receipt");
    expect(tracker.acknowledge("rcp-i") == Outcome::Ok, "ack interrupt receipt");
    expect(tracker.acknowledge("rcp-unknown") == Outcome::Rejected, "unknown ack rejected");
}

void testDuplicateReceiptIdAndIllegalTransitions()
{
    PresentationReceiptTracker tracker;
    expect(tracker.accept("rcp-a", "dlv-1", "att-1", "cores3", 3, 3'000).outcome == Outcome::Ok,
           "accept");
    expect(tracker.accept("rcp-a", "dlv-1", "att-1", "cores3", 3, 3'100).outcome == Outcome::Duplicate,
           "duplicate accept id");
    expect(tracker.accept("rcp-a2", "dlv-2", "att-2", "cores3", 3, 3'200).outcome == Outcome::Rejected,
           "second active delivery rejected");
    expect(tracker.complete("rcp-c", 3'300).outcome == Outcome::Rejected, "complete before start");
    expect(tracker.start("rcp-s", 3'400).outcome == Outcome::Ok, "start");
    expect(tracker.start("rcp-s2", 3'500).outcome == Outcome::Rejected, "double start");
    expect(tracker.cancel("rcp-x", 3'600, "policy").outcome == Outcome::Ok, "cancel from started");
    expect(tracker.status() == Status::Cancelled, "cancelled");
}

void testEncodeMatchesContractShape()
{
    PresentationReceiptTracker tracker;
    const auto accepted =
        tracker.accept("rcp_001", "dlv_001", "att_001", "cores3_001", 1, 1'768'298'460'000ULL);
    expect(accepted.outcome == Outcome::Ok, "accept for encode");

    char buffer[512];
    std::size_t written = 0;
    expect(encodePresentationReceiptJson(*accepted.receipt, buffer, sizeof(buffer), &written),
           "encode ok");
    const std::string json(buffer, written);
    expect(json.find("\"schema_version\":\"0.1\"") != std::string::npos, "schema version");
    expect(json.find("\"status\":\"accepted\"") != std::string::npos, "status");
    expect(json.find("\"receipt_id\":\"rcp_001\"") != std::string::npos, "receipt id");
    expect(json.find("\"generation\":1") != std::string::npos, "generation");
    expect(json.find("\"reported_at\":\"") != std::string::npos, "reported_at present");

    char date[32];
    expect(formatUtcDateTime(0, date, sizeof(date)), "epoch format");
    expect(std::string(date) == "1970-01-01T00:00:00.000Z", "epoch zero");
}

void testFailAndRejectZeroGeneration()
{
    PresentationReceiptTracker tracker;
    expect(tracker.accept("rcp-a", "dlv", "att", "dev", 0, 1).outcome == Outcome::Rejected,
           "generation 0 rejected");
    expect(tracker.accept("rcp-a", "dlv", "att", "dev", 9, 1).outcome == Outcome::Ok, "accept");
    expect(tracker.fail("rcp-f", 2, "oom").outcome == Outcome::Ok, "fail from accepted");
    expect(tracker.status() == Status::Failed, "failed terminal");
}

void testNewDeliveryAfterTerminalAndUnsafeReason()
{
    PresentationReceiptTracker tracker;
    expect(tracker.accept("rcp-a", "dlv-1", "att-1", "dev", 1, 10).outcome == Outcome::Ok, "first");
    expect(tracker.cancel("rcp-x", 11, "revoked").outcome == Outcome::Ok, "cancel");
    expect(tracker.accept("rcp-b", "dlv-2", "att-2", "dev", 2, 12).outcome == Outcome::Ok,
           "new delivery after terminal");
    expect(tracker.interrupt("rcp-i", 13, "bad\"quote").outcome == Outcome::Rejected,
           "unsafe reason rejected");
    expect(tracker.interrupt("rcp-i", 13, "xiaozhi.busy").outcome == Outcome::Ok, "safe reason");
}

void testEncodeGoldenEpochSample()
{
    PresentationReceiptTracker tracker;
    const auto accepted =
        tracker.accept("rcp_001", "dlv_001", "att_001", "cores3_001", 1, 0);
    expect(accepted.outcome == Outcome::Ok, "accept epoch");
    char buffer[512];
    std::size_t written = 0;
    expect(encodePresentationReceiptJson(*accepted.receipt, buffer, sizeof(buffer), &written),
           "encode epoch");
    const char* expected =
        "{\"schema_version\":\"0.1\",\"receipt_id\":\"rcp_001\",\"delivery_id\":\"dlv_001\","
        "\"attempt_id\":\"att_001\",\"device_id\":\"cores3_001\",\"generation\":1,\"status\":\"accepted\","
        "\"reported_at\":\"1970-01-01T00:00:00.000Z\"}";
    expect(std::string(buffer, written) == expected, "golden compact JSON");
}
}  // namespace

int main()
{
    testHappyPathAcceptedStartedCompleted();
    testInterruptFromStartedAndIdempotentAck();
    testDuplicateReceiptIdAndIllegalTransitions();
    testEncodeMatchesContractShape();
    testFailAndRejectZeroGeneration();
    testNewDeliveryAfterTerminalAndUnsafeReason();
    testEncodeGoldenEpochSample();
    return 0;
}
