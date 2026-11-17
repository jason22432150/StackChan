#include "notification_pairing.h"
#include <sdkconfig.h>

#if CONFIG_STACKCHAN_AGENT_NOTIFICATIONS
using namespace setup_workers;
using namespace uitk::lvgl_cpp;
using namespace stackchan::notifications;

NotificationPairingWorker::NotificationPairingWorker()
{
    _panel = std::make_unique<Container>(lv_screen_active());
    _panel->setSize(320, 240);
    _panel->setBgColor(lv_color_hex(0xEDF4FF));
    _panel->setBorderWidth(0);
    _panel->setRadius(0);
    _panel->setScrollDir(LV_DIR_VER);
    lv_obj_set_style_pad_top(_panel->get(), 38, 0);
    lv_obj_set_style_pad_bottom(_panel->get(), 32, 0);
    lv_obj_set_style_pad_row(_panel->get(), 12, 0);
    lv_obj_set_flex_flow(_panel->get(), LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(_panel->get(), LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    _status = std::make_unique<Label>(_panel->get());
    _status->setWidth(280);
    _status->setTextFont(&lv_font_montserrat_16);
    _status->setTextColor(lv_color_hex(0x26206A));
    _status->setLongMode(LV_LABEL_LONG_MODE_WRAP);
    _status->setText("Pair with Coordinator");
    _start = std::make_unique<Button>(_panel->get());
    apply_button_common_style(*_start);
    _start->setSize(280, 44);
    _start->label().setText("Start pairing");
    _start->onClick().connect([this]() { _start_clicked = true; });
    _back = std::make_unique<Button>(_panel->get());
    apply_button_common_style(*_back);
    _back->setSize(280, 44);
    _back->label().setText("Back");
    _back->onClick().connect([this]() { _back_clicked = true; });
}

NotificationPairingWorker::~NotificationPairingWorker() = default;

void NotificationPairingWorker::update()
{
    if (_back_clicked) {
        _session.leave();
        _is_done = true;
        return;
    }
    if (_start_clicked) {
        _start_clicked = false;
        if (!_session.start({CONFIG_STACKCHAN_AGENT_COORDINATOR_HOST, CONFIG_STACKCHAN_AGENT_PAIRING_PORT,
                             CONFIG_STACKCHAN_AGENT_COORDINATOR_CA_PEM},
                            CONFIG_STACKCHAN_AGENT_STREAM_PORT, CONFIG_STACKCHAN_AGENT_COORDINATOR_GENERATION)) {
            _last_text = "Pairing blocked. Check settings, time sync and active connection.";
            _status->setText(_last_text);
        }
    }
    const auto snapshot = _session.poll();
    if (!snapshot) {
        return;
    }
    std::string text;
    bool busy = false;
    bool cancellable = false;
    switch (snapshot->state) {
        case NotificationPairingState::Starting:
            text = "Contacting Coordinator...";
            busy = cancellable = true;
            break;
        case NotificationPairingState::AwaitingApproval:
            text = "Confirm on Coordinator\n" + std::string(snapshot->user_code.data());
            busy = cancellable = true;
            break;
        case NotificationPairingState::Connecting:
            text = "Pairing approved. Connecting...";
            busy = true;
            break;
        case NotificationPairingState::Connected:
            text = "Notifications connected";
            busy = true;
            break;
        case NotificationPairingState::Failed: text = "Pairing or connection failed. Try again."; break;
        case NotificationPairingState::Cancelled: text = "Pairing cancelled"; break;
        case NotificationPairingState::Idle: text = "Notifications disconnected. Pair again."; break;
    }
    if (text != _last_text) {
        _last_text = text;
        _status->setText(text);
    }
    if (busy) {
        _start->addState(LV_STATE_DISABLED);
    } else {
        _start->removeState(LV_STATE_DISABLED);
    }
    _back->label().setText(cancellable ? "Cancel and back" : "Back");
}
#endif
