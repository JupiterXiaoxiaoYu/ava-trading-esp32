# Ava Box reference app UI package.
# Device firmware can add this directory to consume the Ava Box LVGL screens
# without depending on the parent repository's legacy shared UI path.

idf_component_register(
    SRCS
        ui/ave_font_provider.c
        ui/ave_json_utils.c
        ui/ave_price_fmt.c
        ui/ave_screen_manager.c
        ui/ave_transport.c
        ui/screen_browse.c
        ui/screen_confirm.c
        ui/screen_disambiguation.c
        ui/screen_explorer.c
        ui/screen_feed.c
        ui/screen_limit_confirm.c
        ui/screen_notify.c
        ui/screen_portfolio.c
        ui/screen_result.c
        ui/screen_spotlight.c
    INCLUDE_DIRS ui
    REQUIRES lvgl json
)
