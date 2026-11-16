#pragma once

#include "device_stream_ingress.h"

namespace stackchan::notifications {

// Receives one compact JSON frame from an already verified connection.
// The transport supplies the local session and its configured byte limit.
bool receiveDeviceStreamJson(
    DeviceStreamIngress& ingress, DeviceStreamIngress::SessionId session,
    std::string_view json, std::size_t max_bytes, DeviceStreamIngress::Tick now);

}  // namespace stackchan::notifications
