#include <apps/app_setup/workers/notification_pairing_session.h>
#include <cstdlib>
#include <iostream>

using namespace stackchan::notifications;
using setup_workers::NotificationPairingSession;

namespace {
NotificationPairingStatus status;
unsigned requests = 0;
unsigned cancellations = 0;
bool accept = false;

void expect(bool passed, const char* message)
{
    if (!passed) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

const NotificationPairingEndpoint endpoint{"coordinator.example", 9443, "BEGIN\\nfixture\\nEND"};
}

bool stackchan::notifications::requestNotificationProductPairing(
    NotificationPairingEndpoint config, std::uint16_t port, std::uint64_t generation)
{
    ++requests;
    expect(config.coordinator_host == endpoint.coordinator_host && config.port == 9443 && port == 8443 &&
               config.coordinator_ca_pem == "BEGIN\nfixture\nEND" && generation == UINT64_MAX,
           "page passes configured endpoint, PEM line breaks and generation");
    if (accept) {
        status.state = NotificationPairingState::Starting;
    }
    return accept;
}

NotificationPairingStatus stackchan::notifications::notificationProductPairingStatus() { return status; }
void stackchan::notifications::cancelNotificationProductPairing() noexcept { ++cancellations; }

int main()
{
    {
        NotificationPairingSession page;
        expect(!page.poll() && requests == 0, "opening a page performs no request");
        for (auto generation : {"", "-1", " 1", "1x", "18446744073709551616"}) {
            expect(!page.start(endpoint, 8443, generation) && requests == 0, "invalid generation schedules no worker");
        }
        expect(!page.start(endpoint, 8443, "18446744073709551615"), "busy or blocked request is reported");
    }
    expect(cancellations == 0, "a rejected page cannot cancel another worker");
    accept = true;
    {
        NotificationPairingSession page;
        expect(page.start(endpoint, 8443, "18446744073709551615"), "click starts a request");
        expect(!page.start(endpoint, 8443, "18446744073709551615"), "duplicate click is ignored");
        status.state = NotificationPairingState::AwaitingApproval;
        status.user_code = {'A', 'B', 'C', '1', '2', '3', '\0'};
        const auto snapshot = page.poll();
        expect(snapshot && snapshot->user_code == status.user_code, "UI receives only the task snapshot");
    }
    expect(cancellations == 1, "leaving while awaiting approval cancels the owned request");
    {
        NotificationPairingSession page;
        expect(page.start(endpoint, 8443, "18446744073709551615"), "retry starts another request");
        status.state = NotificationPairingState::Connecting;
        expect(page.poll()->state == NotificationPairingState::Connecting, "UI observes connection in progress");
        status.state = NotificationPairingState::Connected;
        expect(page.poll()->state == NotificationPairingState::Connected, "UI continues observing after approval");
        page.leave();
        page.leave();
    }
    expect(cancellations == 1, "leaving a connected page keeps the active notification stream");
    for (auto terminal : {NotificationPairingState::Failed, NotificationPairingState::Cancelled, NotificationPairingState::Idle}) {
        NotificationPairingSession page;
        expect(page.start(endpoint, 8443, "18446744073709551615"), "terminal transition can be observed");
        status = {};
        status.state = terminal;
        expect(page.poll()->state == terminal && !page.poll(), "terminal state is delivered and releases page ownership");
        status.state = NotificationPairingState::Starting;
    }
    expect(cancellations == 1, "completed page cannot cancel a later worker");
}
