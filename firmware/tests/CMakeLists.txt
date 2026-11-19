cmake_minimum_required(VERSION 3.16)

project(stackchan_firmware_tests LANGUAGES CXX)

enable_testing()
if(NOT WIN32)
    find_package(Threads REQUIRED)
endif()

foreach(target hal_nvs_init_test hal_nvs_init_encrypted_test)
    add_executable(${target} hal_nvs_init_test.cpp)
    target_include_directories(${target} PRIVATE nvs_fakes ../main)
    target_compile_features(${target} PRIVATE cxx_std_17)
    add_test(NAME ${target} COMMAND $<TARGET_FILE:${target}>)
endforeach()
target_compile_definitions(hal_nvs_init_encrypted_test PRIVATE CONFIG_NVS_ENCRYPTION=1)

add_executable(notification_pairing_session_test notification_pairing_session_test.cpp)
target_include_directories(notification_pairing_session_test PRIVATE tls_fakes ../main)
target_compile_features(notification_pairing_session_test PRIVATE cxx_std_20)
add_test(NAME notification_pairing_session_test COMMAND $<TARGET_FILE:notification_pairing_session_test>)

foreach(target notification_product_task_test notification_product_task_disabled_test
               notification_product_task_diagnostics_test)
    add_executable(${target}
        notification_product_task_test.cpp
        ../main/stackchan/notifications/notification_product_task.cpp
    )
    target_include_directories(${target} PRIVATE task_fakes tls_fakes nvs_fakes ../main)
    target_compile_features(${target} PRIVATE cxx_std_20)
    add_test(NAME ${target} COMMAND $<TARGET_FILE:${target}>)
endforeach()
target_compile_definitions(notification_product_task_test PRIVATE CONFIG_STACKCHAN_AGENT_NOTIFICATIONS=1)
target_compile_definitions(notification_product_task_diagnostics_test PRIVATE
    CONFIG_STACKCHAN_AGENT_NOTIFICATIONS=1 CONFIG_STACKCHAN_RUNTIME_BASELINE=1
)

foreach(target notification_credentials_test notification_credentials_unencrypted_test)
    add_executable(${target}
        notification_credentials_test.cpp
        ../main/stackchan/notifications/notification_credentials.cpp
    )
    target_include_directories(${target} PRIVATE nvs_fakes ../main)
    target_compile_features(${target} PRIVATE cxx_std_20)
    if(TARGET Threads::Threads)
        target_link_libraries(${target} PRIVATE Threads::Threads)
    endif()
    add_test(NAME ${target} COMMAND $<TARGET_FILE:${target}>)
endforeach()
target_compile_definitions(notification_credentials_test PRIVATE CONFIG_NVS_ENCRYPTION=1)

add_executable(motion_math_test
    motion_math_test.cpp
    ../main/stackchan/motion/motion_math.cpp
)

target_include_directories(motion_math_test PRIVATE
    ../main
)

target_compile_features(motion_math_test PRIVATE cxx_std_20)

if(MSVC)
    target_compile_definitions(motion_math_test PRIVATE _USE_MATH_DEFINES)
endif()

add_test(NAME motion_math_test COMMAND $<TARGET_FILE:motion_math_test>)

add_executable(notification_controller_test
    notification_controller_test.cpp
    ../main/stackchan/notifications/notification_controller.cpp
)
target_include_directories(notification_controller_test PRIVATE ../main)
target_compile_features(notification_controller_test PRIVATE cxx_std_17)
add_test(NAME notification_controller_test COMMAND $<TARGET_FILE:notification_controller_test>)

add_executable(resource_arbiter_test
    resource_arbiter_test.cpp
    ../main/stackchan/notifications/resource_arbiter.cpp
)
target_include_directories(resource_arbiter_test PRIVATE ../main)
target_compile_features(resource_arbiter_test PRIVATE cxx_std_17)
add_test(NAME resource_arbiter_test COMMAND $<TARGET_FILE:resource_arbiter_test>)

add_executable(presentation_receipt_test
    presentation_receipt_test.cpp
    ../main/stackchan/notifications/presentation_receipt.cpp
)
target_include_directories(presentation_receipt_test PRIVATE ../main)
target_compile_features(presentation_receipt_test PRIVATE cxx_std_17)
add_test(NAME presentation_receipt_test COMMAND $<TARGET_FILE:presentation_receipt_test>)

# Presenter 已可選掛 Motion；凡連結 notification_presenter.cpp 者需一併連結。
set(STACKCHAN_NOTICE_MOTION_SOURCES
    ../main/stackchan/notifications/notice_motion_plan.cpp
    ../main/stackchan/notifications/notification_motion_reactor.cpp
)

add_executable(notification_presenter_test
    notification_presenter_test.cpp
    ../main/stackchan/notifications/notification_presenter.cpp
    ${STACKCHAN_NOTICE_MOTION_SOURCES}
    ../main/stackchan/notifications/resource_arbiter.cpp
)
target_include_directories(notification_presenter_test PRIVATE ../main)
target_compile_features(notification_presenter_test PRIVATE cxx_std_17)
add_test(NAME notification_presenter_test COMMAND $<TARGET_FILE:notification_presenter_test>)

add_executable(basic_notice_text_test
    basic_notice_text_test.cpp
    ../main/stackchan/notifications/basic_notice_text.cpp
)
target_include_directories(basic_notice_text_test PRIVATE ../main)
target_compile_features(basic_notice_text_test PRIVATE cxx_std_17)
add_test(NAME basic_notice_text_test COMMAND $<TARGET_FILE:basic_notice_text_test>)

add_executable(avatar_speech_ui_test
    avatar_speech_ui_test.cpp
    ../main/stackchan/notifications/avatar_speech_ui.cpp
    ../main/stackchan/notifications/basic_notice_text.cpp
)
target_include_directories(avatar_speech_ui_test PRIVATE ../main)
target_compile_features(avatar_speech_ui_test PRIVATE cxx_std_17)
add_test(NAME avatar_speech_ui_test COMMAND $<TARGET_FILE:avatar_speech_ui_test>)

add_executable(notice_motion_plan_test
    notice_motion_plan_test.cpp
    ../main/stackchan/notifications/notice_motion_plan.cpp
)
target_include_directories(notice_motion_plan_test PRIVATE ../main)
target_compile_features(notice_motion_plan_test PRIVATE cxx_std_17)
add_test(NAME notice_motion_plan_test COMMAND $<TARGET_FILE:notice_motion_plan_test>)

add_executable(notification_motion_reactor_test
    notification_motion_reactor_test.cpp
    ../main/stackchan/notifications/notification_presenter.cpp
    ${STACKCHAN_NOTICE_MOTION_SOURCES}
    ../main/stackchan/notifications/resource_arbiter.cpp
)
target_include_directories(notification_motion_reactor_test PRIVATE ../main)
target_compile_features(notification_motion_reactor_test PRIVATE cxx_std_17)
add_test(NAME notification_motion_reactor_test COMMAND $<TARGET_FILE:notification_motion_reactor_test>)

add_executable(xiaozhi_priority_tick_test
    xiaozhi_priority_tick_test.cpp
    ../main/stackchan/notifications/xiaozhi_priority_tick.cpp
    ../main/stackchan/notifications/notification_presenter.cpp
    ${STACKCHAN_NOTICE_MOTION_SOURCES}
    ../main/stackchan/notifications/resource_arbiter.cpp
)
target_include_directories(xiaozhi_priority_tick_test PRIVATE ../main)
target_compile_features(xiaozhi_priority_tick_test PRIVATE cxx_std_17)
add_test(NAME xiaozhi_priority_tick_test COMMAND $<TARGET_FILE:xiaozhi_priority_tick_test>)

add_executable(fail_closed_guard_test
    fail_closed_guard_test.cpp
    ../main/stackchan/notifications/fail_closed_guard.cpp
    ../main/stackchan/notifications/notification_presenter.cpp
    ${STACKCHAN_NOTICE_MOTION_SOURCES}
    ../main/stackchan/notifications/resource_arbiter.cpp
    ../main/stackchan/notifications/notification_controller.cpp
    ../main/stackchan/notifications/presentation_receipt.cpp
)
target_include_directories(fail_closed_guard_test PRIVATE ../main)
target_compile_features(fail_closed_guard_test PRIVATE cxx_std_17)
add_test(NAME fail_closed_guard_test COMMAND $<TARGET_FILE:fail_closed_guard_test>)

add_executable(fail_closed_budget_test
    fail_closed_budget_test.cpp
    ../main/stackchan/notifications/fail_closed_budget.cpp
    ../main/stackchan/notifications/fail_closed_guard.cpp
    ../main/stackchan/notifications/notification_presenter.cpp
    ${STACKCHAN_NOTICE_MOTION_SOURCES}
    ../main/stackchan/notifications/resource_arbiter.cpp
    ../main/stackchan/notifications/notification_controller.cpp
    ../main/stackchan/notifications/presentation_receipt.cpp
    ../main/stackchan/notifications/runtime_limits.cpp
)
target_include_directories(fail_closed_budget_test PRIVATE ../main)
target_compile_features(fail_closed_budget_test PRIVATE cxx_std_17)
add_test(NAME fail_closed_budget_test COMMAND $<TARGET_FILE:fail_closed_budget_test>)

add_executable(fail_closed_revoke_probe_test
    fail_closed_revoke_probe_test.cpp
    ../main/stackchan/notifications/fail_closed_revoke_probe.cpp
    ../main/stackchan/notifications/fail_closed_budget.cpp
    ../main/stackchan/notifications/fail_closed_guard.cpp
    ../main/stackchan/notifications/notification_presenter.cpp
    ${STACKCHAN_NOTICE_MOTION_SOURCES}
    ../main/stackchan/notifications/resource_arbiter.cpp
    ../main/stackchan/notifications/notification_controller.cpp
    ../main/stackchan/notifications/presentation_receipt.cpp
    ../main/stackchan/notifications/runtime_limits.cpp
)
target_include_directories(fail_closed_revoke_probe_test PRIVATE ../main)
target_compile_features(fail_closed_revoke_probe_test PRIVATE cxx_std_17)
add_test(NAME fail_closed_revoke_probe_test COMMAND $<TARGET_FILE:fail_closed_revoke_probe_test>)

add_executable(notification_product_loop_test
    notification_product_loop_test.cpp
    ../main/stackchan/notifications/notification_product_loop.cpp
    ../main/stackchan/notifications/basic_notice_text.cpp
    ../main/stackchan/notifications/fail_closed_guard.cpp
    ../main/stackchan/notifications/notification_presenter.cpp
    ${STACKCHAN_NOTICE_MOTION_SOURCES}
    ../main/stackchan/notifications/resource_arbiter.cpp
    ../main/stackchan/notifications/notification_controller.cpp
    ../main/stackchan/notifications/presentation_receipt.cpp
    ../main/stackchan/notifications/device_stream_ingress.cpp
)
target_include_directories(notification_product_loop_test PRIVATE ../main)
target_compile_features(notification_product_loop_test PRIVATE cxx_std_17)
add_test(NAME notification_product_loop_test COMMAND $<TARGET_FILE:notification_product_loop_test>)

add_executable(notification_audio_policy_test
    notification_audio_policy_test.cpp
    ../main/stackchan/notifications/notification_audio_policy.cpp
    ../main/stackchan/notifications/resource_arbiter.cpp
)
target_include_directories(notification_audio_policy_test PRIVATE ../main)
target_compile_features(notification_audio_policy_test PRIVATE cxx_std_17)
add_test(NAME notification_audio_policy_test COMMAND $<TARGET_FILE:notification_audio_policy_test>)

add_executable(runtime_limits_test
    runtime_limits_test.cpp
    ../main/stackchan/notifications/runtime_limits.cpp
    ../main/stackchan/notifications/notification_controller.cpp
)
target_include_directories(runtime_limits_test PRIVATE ../main)
target_compile_features(runtime_limits_test PRIVATE cxx_std_17)
add_test(NAME runtime_limits_test COMMAND $<TARGET_FILE:runtime_limits_test>)

add_executable(device_stream_ingress_test
    device_stream_ingress_test.cpp
    ../main/stackchan/notifications/device_stream_ingress.cpp
    ../main/stackchan/notifications/notification_controller.cpp
)
target_include_directories(device_stream_ingress_test PRIVATE ../main)
target_compile_features(device_stream_ingress_test PRIVATE cxx_std_17)
add_test(NAME device_stream_ingress_test COMMAND $<TARGET_FILE:device_stream_ingress_test>)

add_executable(personal_pending_ingress_test
    personal_pending_ingress_test.cpp
    ../main/stackchan/notifications/personal_pending_ingress.cpp
    ../main/stackchan/notifications/notification_controller.cpp
)
target_include_directories(personal_pending_ingress_test PRIVATE ../main)
target_compile_features(personal_pending_ingress_test PRIVATE cxx_std_17)
add_test(NAME personal_pending_ingress_test COMMAND $<TARGET_FILE:personal_pending_ingress_test>)

# The firmware fetch_repos.py step supplies the pinned ArduinoJson source.
set(ARDUINO_JSON_INCLUDE "${CMAKE_CURRENT_SOURCE_DIR}/../components/ArduinoJson/src")
if(EXISTS "${ARDUINO_JSON_INCLUDE}/ArduinoJson.h")
    add_executable(device_stream_json_test
        device_stream_json_test.cpp
        ../main/stackchan/notifications/device_stream_json.cpp
        ../main/stackchan/notifications/device_stream_ingress.cpp
        ../main/stackchan/notifications/notification_controller.cpp
    )
    target_include_directories(device_stream_json_test PRIVATE ../main "${ARDUINO_JSON_INCLUDE}")
    target_compile_features(device_stream_json_test PRIVATE cxx_std_17)
    add_test(NAME device_stream_json_test COMMAND $<TARGET_FILE:device_stream_json_test>)

    add_executable(device_stream_tls_client_test
        device_stream_tls_client_test.cpp
        ../main/stackchan/notifications/device_stream_tls_client.cpp
        ../main/stackchan/notifications/device_stream_json.cpp
        ../main/stackchan/notifications/device_stream_ingress.cpp
        ../main/stackchan/notifications/notification_controller.cpp
    )
    target_include_directories(device_stream_tls_client_test PRIVATE tls_fakes ../main "${ARDUINO_JSON_INCLUDE}")
    target_compile_features(device_stream_tls_client_test PRIVATE cxx_std_20)
    add_test(NAME device_stream_tls_client_test COMMAND $<TARGET_FILE:device_stream_tls_client_test>)

    add_executable(policy_lease_test
        policy_lease_test.cpp
        ../main/stackchan/notifications/policy_lease.cpp
    )
    target_include_directories(policy_lease_test PRIVATE ../main "${ARDUINO_JSON_INCLUDE}")
    target_compile_features(policy_lease_test PRIVATE cxx_std_17)
    add_test(NAME policy_lease_test COMMAND $<TARGET_FILE:policy_lease_test>)

    add_executable(policy_lease_http_client_test
        policy_lease_http_client_test.cpp
        ../main/stackchan/notifications/policy_lease_http_client.cpp
        ../main/stackchan/notifications/coordinator_https.cpp
        ../main/stackchan/notifications/policy_lease.cpp
    )
    target_include_directories(policy_lease_http_client_test PRIVATE tls_fakes ../main "${ARDUINO_JSON_INCLUDE}")
    target_compile_features(policy_lease_http_client_test PRIVATE cxx_std_20)
    add_test(NAME policy_lease_http_client_test COMMAND $<TARGET_FILE:policy_lease_http_client_test>)

    add_executable(stream_provision_test
        stream_provision_test.cpp
        ../main/stackchan/notifications/stream_provision.cpp
        ../main/stackchan/notifications/policy_lease.cpp
        ../main/stackchan/notifications/runtime_limits.cpp
    )
    target_include_directories(stream_provision_test PRIVATE tls_fakes ../main "${ARDUINO_JSON_INCLUDE}")
    target_compile_features(stream_provision_test PRIVATE cxx_std_20)
    add_test(NAME stream_provision_test COMMAND $<TARGET_FILE:stream_provision_test>)

    add_executable(fetch_and_provision_test
        fetch_and_provision_test.cpp
        ../main/stackchan/notifications/stream_bootstrap.cpp
        ../main/stackchan/notifications/stream_provision.cpp
        ../main/stackchan/notifications/policy_lease_http_client.cpp
        ../main/stackchan/notifications/coordinator_https.cpp
        ../main/stackchan/notifications/policy_lease.cpp
        ../main/stackchan/notifications/runtime_limits.cpp
    )
    target_include_directories(fetch_and_provision_test PRIVATE tls_fakes ../main "${ARDUINO_JSON_INCLUDE}")
    target_compile_features(fetch_and_provision_test PRIVATE cxx_std_20)
    add_test(NAME fetch_and_provision_test COMMAND $<TARGET_FILE:fetch_and_provision_test>)

    add_executable(start_provisioned_stream_test
        start_provisioned_stream_test.cpp
        ../main/stackchan/notifications/notification_pairing_client.cpp
        ../main/stackchan/notifications/notification_credentials.cpp
        ../main/stackchan/notifications/notification_product_runtime.cpp
        ../main/stackchan/notifications/notification_product_loop.cpp
        ../main/stackchan/notifications/basic_notice_text.cpp
        ../main/stackchan/notifications/avatar_speech_ui.cpp
        ../main/stackchan/notifications/notification_product_loop_poll.cpp
        ../main/stackchan/notifications/notification_presenter.cpp
        ${STACKCHAN_NOTICE_MOTION_SOURCES}
        ../main/stackchan/notifications/xiaozhi_priority_tick.cpp
        ../main/stackchan/notifications/fail_closed_guard.cpp
        ../main/stackchan/notifications/resource_arbiter.cpp
        ../main/stackchan/notifications/presentation_receipt.cpp
        ../main/stackchan/notifications/stream_session_start.cpp
        ../main/stackchan/notifications/stream_bootstrap.cpp
        ../main/stackchan/notifications/stream_provision.cpp
        ../main/stackchan/notifications/policy_lease_http_client.cpp
        ../main/stackchan/notifications/coordinator_https.cpp
        ../main/stackchan/notifications/policy_lease.cpp
        ../main/stackchan/notifications/runtime_limits.cpp
        ../main/stackchan/notifications/device_stream_tls_client.cpp
        ../main/stackchan/notifications/device_stream_json.cpp
        ../main/stackchan/notifications/device_stream_ingress.cpp
        ../main/stackchan/notifications/personal_pending_ingress.cpp
        ../main/stackchan/notifications/personal_pending_json.cpp
        ../main/stackchan/notifications/notification_controller.cpp
    )
    target_include_directories(start_provisioned_stream_test PRIVATE tls_fakes nvs_fakes ../main "${ARDUINO_JSON_INCLUDE}")
    if(TARGET Threads::Threads)
        target_link_libraries(start_provisioned_stream_test PRIVATE Threads::Threads)
    endif()
    target_compile_features(start_provisioned_stream_test PRIVATE cxx_std_20)
    add_test(NAME start_provisioned_stream_test COMMAND $<TARGET_FILE:start_provisioned_stream_test>)
    add_test(NAME notification_pairing_after_restart_test COMMAND $<TARGET_FILE:start_provisioned_stream_test> --after-restart)
    add_test(NAME notification_pairing_https_test COMMAND $<TARGET_FILE:start_provisioned_stream_test> --pairing-https)

    add_executable(device_loopback_handshake_test
        device_loopback_handshake_test.cpp
        ../main/stackchan/notifications/device_loopback_handshake.cpp
        ../main/stackchan/notifications/stream_provision.cpp
        ../main/stackchan/notifications/policy_lease.cpp
        ../main/stackchan/notifications/runtime_limits.cpp
        ../main/stackchan/notifications/device_stream_json.cpp
        ../main/stackchan/notifications/device_stream_ingress.cpp
        ../main/stackchan/notifications/notification_controller.cpp
    )
    target_include_directories(device_loopback_handshake_test PRIVATE tls_fakes ../main "${ARDUINO_JSON_INCLUDE}")
    target_compile_features(device_loopback_handshake_test PRIVATE cxx_std_17)
    add_test(NAME device_loopback_handshake_test COMMAND $<TARGET_FILE:device_loopback_handshake_test>)

    add_executable(notification_product_loop_poll_test
        notification_product_loop_poll_test.cpp
        ../main/stackchan/notifications/notification_product_loop.cpp
        ../main/stackchan/notifications/basic_notice_text.cpp
        ../main/stackchan/notifications/notification_product_loop_poll.cpp
        ../main/stackchan/notifications/fail_closed_guard.cpp
        ../main/stackchan/notifications/notification_presenter.cpp
        ${STACKCHAN_NOTICE_MOTION_SOURCES}
        ../main/stackchan/notifications/resource_arbiter.cpp
        ../main/stackchan/notifications/notification_controller.cpp
        ../main/stackchan/notifications/presentation_receipt.cpp
        ../main/stackchan/notifications/runtime_limits.cpp
        ../main/stackchan/notifications/device_stream_tls_client.cpp
        ../main/stackchan/notifications/device_stream_json.cpp
        ../main/stackchan/notifications/device_stream_ingress.cpp
        ../main/stackchan/notifications/personal_pending_ingress.cpp
        ../main/stackchan/notifications/personal_pending_json.cpp
    )
    target_include_directories(notification_product_loop_poll_test PRIVATE tls_fakes ../main "${ARDUINO_JSON_INCLUDE}")
    target_compile_features(notification_product_loop_poll_test PRIVATE cxx_std_20)
    add_test(NAME notification_product_loop_poll_test COMMAND $<TARGET_FILE:notification_product_loop_poll_test>)

    add_executable(personal_pending_product_loop_test
        personal_pending_product_loop_test.cpp
        ../main/stackchan/notifications/notification_product_loop.cpp
        ../main/stackchan/notifications/basic_notice_text.cpp
        ../main/stackchan/notifications/fail_closed_guard.cpp
        ../main/stackchan/notifications/notification_presenter.cpp
        ${STACKCHAN_NOTICE_MOTION_SOURCES}
        ../main/stackchan/notifications/resource_arbiter.cpp
        ../main/stackchan/notifications/notification_controller.cpp
        ../main/stackchan/notifications/presentation_receipt.cpp
        ../main/stackchan/notifications/personal_pending_ingress.cpp
        ../main/stackchan/notifications/personal_pending_json.cpp
    )
    target_include_directories(personal_pending_product_loop_test PRIVATE ../main "${ARDUINO_JSON_INCLUDE}")
    target_compile_features(personal_pending_product_loop_test PRIVATE cxx_std_17)
    add_test(NAME personal_pending_product_loop_test COMMAND $<TARGET_FILE:personal_pending_product_loop_test>)
endif()
