cmake_minimum_required(VERSION 3.12)

# Shared AVE screen library
# Used by both the PC simulator and the ESP32 firmware (via soft-link)

add_library(shared_ave_screens STATIC
    ave_screen_manager.c
    ave_price_fmt.c
    ave_transport.c
    screen_feed.c
    screen_spotlight.c
    screen_confirm.c
    screen_limit_confirm.c
    screen_result.c
    screen_portfolio.c
    screen_notify.c
    screen_disambiguation.c
)

target_include_directories(shared_ave_screens PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
)

# Link against LVGL (provided by parent project)
target_link_libraries(shared_ave_screens PUBLIC lvgl)

# Math library for log10()
target_link_libraries(shared_ave_screens PUBLIC m)
