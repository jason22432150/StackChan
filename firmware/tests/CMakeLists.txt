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
