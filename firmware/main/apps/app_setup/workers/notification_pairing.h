#pragma once

#include "workers.h"
#include "notification_pairing_session.h"

namespace setup_workers {

class NotificationPairingWorker : public WorkerBase {
public:
    NotificationPairingWorker();
    ~NotificationPairingWorker() override;
    void update() override;

private:
    NotificationPairingSession _session;
    std::unique_ptr<uitk::lvgl_cpp::Container> _panel;
    std::unique_ptr<uitk::lvgl_cpp::Label> _status;
    std::unique_ptr<uitk::lvgl_cpp::Button> _start, _back;
    bool _start_clicked = false;
    bool _back_clicked = false;
    std::string _last_text;
};

}  // namespace setup_workers
