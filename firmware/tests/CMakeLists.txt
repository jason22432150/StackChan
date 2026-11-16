cmake_minimum_required(VERSION 3.16)

project(stackchan_firmware_tests LANGUAGES CXX)

enable_testing()

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
        ../main/stackchan/notifications/policy_lease.cpp
    )
    target_include_directories(policy_lease_http_client_test PRIVATE tls_fakes ../main "${ARDUINO_JSON_INCLUDE}")
    target_compile_features(policy_lease_http_client_test PRIVATE cxx_std_20)
    add_test(NAME policy_lease_http_client_test COMMAND $<TARGET_FILE:policy_lease_http_client_test>)
endif()
