#include "ava_devicekit_ui.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int json_str(const char *json, const char *key, char *out, size_t out_n);
static int json_str_copy(const char *p, char *out, size_t out_n);
static const char *json_data_ptr(const char *json, size_t *len);
static int emit(ava_dk_ui_runtime_t *rt, const char *json);
static void cancel_screen_timers(ava_dk_ui_runtime_t *rt, ava_dk_screen_id_t next);
static int find_custom_screen(const ava_dk_ui_runtime_t *rt, const char *name);
static ava_dk_screen_vtable_t *current_screen_vtable(ava_dk_ui_runtime_t *rt);
static const char *safe_str(const char *value);

void ava_dk_ui_init(ava_dk_ui_runtime_t *rt)
{
    if (!rt) return;
    memset(rt, 0, sizeof(*rt));
    rt->current = AVA_DK_SCREEN_FEED;
    rt->current_custom_index = -1;
    rt->back_target = AVA_DK_SCREEN_FEED;
}

void ava_dk_ui_set_transport(ava_dk_ui_runtime_t *rt, ava_dk_send_json_fn send_json, void *user)
{
    if (!rt) return;
    rt->send_json = send_json;
    rt->send_user = user;
}

void ava_dk_ui_register_screen(ava_dk_ui_runtime_t *rt, ava_dk_screen_id_t id, ava_dk_screen_vtable_t screen)
{
    if (!rt || id < 0 || id >= AVA_DK_SCREEN_UNKNOWN) return;
    rt->screens[id] = screen;
}

int ava_dk_ui_register_custom_screen(ava_dk_ui_runtime_t *rt, ava_dk_screen_contract_t contract, ava_dk_screen_vtable_t screen)
{
    int idx;
    if (!rt || !contract.screen_id || !contract.screen_id[0]) return 0;
    idx = find_custom_screen(rt, contract.screen_id);
    if (idx < 0) {
        if (rt->custom_screen_count >= AVA_DK_MAX_CUSTOM_SCREENS) return 0;
        idx = rt->custom_screen_count++;
    }
    rt->custom_contracts[idx] = contract;
    rt->custom_screens[idx] = screen;
    return 1;
}

ava_dk_screen_id_t ava_dk_ui_screen_from_name(const char *name)
{
    if (!name) return AVA_DK_SCREEN_UNKNOWN;
    if (strcmp(name, "feed") == 0) return AVA_DK_SCREEN_FEED;
    if (strcmp(name, "browse") == 0 || strcmp(name, "watchlist") == 0) return AVA_DK_SCREEN_BROWSE;
    if (strcmp(name, "spotlight") == 0) return AVA_DK_SCREEN_SPOTLIGHT;
    if (strcmp(name, "portfolio") == 0) return AVA_DK_SCREEN_PORTFOLIO;
    if (strcmp(name, "confirm") == 0) return AVA_DK_SCREEN_CONFIRM;
    if (strcmp(name, "limit_confirm") == 0) return AVA_DK_SCREEN_LIMIT_CONFIRM;
    if (strcmp(name, "result") == 0) return AVA_DK_SCREEN_RESULT;
    if (strcmp(name, "notify") == 0) return AVA_DK_SCREEN_NOTIFY;
    if (strcmp(name, "disambiguation") == 0) return AVA_DK_SCREEN_DISAMBIGUATION;
    return AVA_DK_SCREEN_UNKNOWN;
}

const char *ava_dk_ui_screen_name(ava_dk_screen_id_t id)
{
    switch (id) {
    case AVA_DK_SCREEN_FEED: return "feed";
    case AVA_DK_SCREEN_BROWSE: return "browse";
    case AVA_DK_SCREEN_SPOTLIGHT: return "spotlight";
    case AVA_DK_SCREEN_PORTFOLIO: return "portfolio";
    case AVA_DK_SCREEN_CONFIRM: return "confirm";
    case AVA_DK_SCREEN_LIMIT_CONFIRM: return "limit_confirm";
    case AVA_DK_SCREEN_RESULT: return "result";
    case AVA_DK_SCREEN_NOTIFY: return "notify";
    case AVA_DK_SCREEN_DISAMBIGUATION: return "disambiguation";
    default: return "unknown";
    }
}

const char *ava_dk_ui_current_screen_name(const ava_dk_ui_runtime_t *rt)
{
    if (!rt) return "unknown";
    if (rt->current == AVA_DK_SCREEN_UNKNOWN &&
        rt->current_custom_index >= 0 &&
        rt->current_custom_index < rt->custom_screen_count) {
        return safe_str(rt->custom_contracts[rt->current_custom_index].screen_id);
    }
    return ava_dk_ui_screen_name(rt->current);
}

ava_dk_screen_id_t ava_dk_ui_current_screen(const ava_dk_ui_runtime_t *rt)
{
    return rt ? rt->current : AVA_DK_SCREEN_UNKNOWN;
}

int ava_dk_ui_handle_display_json(ava_dk_ui_runtime_t *rt, const char *json)
{
    char screen_name[40] = {0};
    size_t data_len = 0;
    const char *data_start = NULL;
    char *data = NULL;
    ava_dk_screen_id_t screen_id;
    ava_dk_screen_vtable_t *screen;
    int custom_idx = -1;

    if (!rt || !json) return 0;
    if (!json_str(json, "screen", screen_name, sizeof(screen_name))) return 0;
    screen_id = ava_dk_ui_screen_from_name(screen_name);
    if (screen_id == AVA_DK_SCREEN_UNKNOWN) {
        custom_idx = find_custom_screen(rt, screen_name);
        if (custom_idx < 0) return 0;
    }

    data_start = json_data_ptr(json, &data_len);
    data = (char *)malloc(data_len + 1);
    if (!data) return 0;
    memcpy(data, data_start, data_len);
    data[data_len] = '\0';

    screen = custom_idx >= 0 ? &rt->custom_screens[custom_idx] : &rt->screens[screen_id];
    if (screen->show) {
        if (screen_id != AVA_DK_SCREEN_NOTIFY) {
            cancel_screen_timers(rt, screen_id);
            if (rt->current == AVA_DK_SCREEN_FEED || rt->current == AVA_DK_SCREEN_BROWSE || rt->current == AVA_DK_SCREEN_PORTFOLIO) {
                rt->back_target = rt->current;
            }
            rt->current = screen_id;
            rt->current_custom_index = custom_idx;
        }
        screen->show(data, screen->user);
    }

    free(data);
    return 1;
}

int ava_dk_ui_key_press(ava_dk_ui_runtime_t *rt, ava_dk_key_t key)
{
    ava_dk_screen_vtable_t *screen;
    char context[768] = {0};

    if (!rt) return 0;

    if (key == AVA_DK_KEY_Y && rt->current != AVA_DK_SCREEN_PORTFOLIO) {
        return emit(rt, "{\"type\":\"key_action\",\"action\":\"portfolio\"}");
    }

    if (key == AVA_DK_KEY_FN) {
        int has_context = 0;
        screen = current_screen_vtable(rt);
        if (screen && screen->selection_context_json) {
            has_context = screen->selection_context_json(context, sizeof(context), screen->user);
        }
        if (has_context) {
            char msg[1024];
            snprintf(msg, sizeof(msg), "{\"type\":\"listen_detect\",\"context\":%s}", context);
            return emit(rt, msg);
        }
        return emit(rt, "{\"type\":\"listen_detect\"}");
    }

    screen = current_screen_vtable(rt);
    if (!screen || !screen->key) return 0;
    screen->key(key, screen->user);
    return 1;
}

int ava_dk_ui_emit_input_event(ava_dk_ui_runtime_t *rt, const ava_dk_input_event_t *event, const char *context_json)
{
    char msg[1024];
    if (!ava_dk_ui_build_input_event_json(event, context_json, msg, sizeof(msg))) return 0;
    return emit(rt, msg);
}

int ava_dk_ui_build_input_event_json(const ava_dk_input_event_t *event, const char *context_json, char *out, size_t out_n)
{
    char source[96];
    char kind[96];
    char code[96];
    char action[128];
    int n;
    if (!event || !out || out_n == 0) return 0;
    if (!ava_dk_ui_json_escape(safe_str(event->source), source, sizeof(source))) return 0;
    if (!ava_dk_ui_json_escape(safe_str(event->kind), kind, sizeof(kind))) return 0;
    if (!ava_dk_ui_json_escape(safe_str(event->code), code, sizeof(code))) return 0;
    if (!ava_dk_ui_json_escape(safe_str(event->semantic_action), action, sizeof(action))) return 0;
    n = snprintf(
        out,
        out_n,
        "{\"type\":\"input_event\",\"source\":\"%s\",\"kind\":\"%s\",\"code\":\"%s\",\"semantic_action\":\"%s\",\"value\":%d,\"x\":%d,\"y\":%d",
        source,
        kind,
        code,
        action,
        event->value,
        event->x,
        event->y);
    if (n <= 0 || (size_t)n >= out_n) return 0;
    if (context_json && context_json[0]) {
        int m = snprintf(out + n, out_n - (size_t)n, ",\"context\":%s}", context_json);
        return m > 0 && (size_t)m < out_n - (size_t)n;
    }
    return snprintf(out + n, out_n - (size_t)n, "}") < (int)(out_n - (size_t)n);
}

int ava_dk_ui_build_key_action_json(const char *action, const char *extra_fields_json, char *out, size_t out_n)
{
    char escaped[128];
    if (!action || !out || out_n == 0) return 0;
    if (!ava_dk_ui_json_escape(action, escaped, sizeof(escaped))) return 0;
    if (extra_fields_json && extra_fields_json[0]) {
        return snprintf(out, out_n, "{\"type\":\"key_action\",\"action\":\"%s\",%s}", escaped, extra_fields_json) < (int)out_n;
    }
    return snprintf(out, out_n, "{\"type\":\"key_action\",\"action\":\"%s\"}", escaped) < (int)out_n;
}

int ava_dk_ui_build_listen_detect_json(const char *text, const char *selection_context_json, char *out, size_t out_n)
{
    char escaped[512];
    if (!out || out_n == 0) return 0;
    if (!ava_dk_ui_json_escape(text ? text : "", escaped, sizeof(escaped))) return 0;
    if (selection_context_json && selection_context_json[0]) {
        return snprintf(out, out_n, "{\"type\":\"listen_detect\",\"text\":\"%s\",\"context\":%s}", escaped, selection_context_json) < (int)out_n;
    }
    return snprintf(out, out_n, "{\"type\":\"listen_detect\",\"text\":\"%s\"}", escaped) < (int)out_n;
}

int ava_dk_ui_json_escape(const char *src, char *out, size_t out_n)
{
    size_t w = 0;
    if (!src || !out || out_n == 0) return 0;
    for (; *src; src++) {
        char c = *src;
        const char *rep = NULL;
        if (c == '\\') rep = "\\\\";
        else if (c == '"') rep = "\\\"";
        else if (c == '\n') rep = "\\n";
        else if (c == '\r') rep = "\\r";
        else if (c == '\t') rep = "\\t";
        if (rep) {
            size_t n = strlen(rep);
            if (w + n >= out_n) return 0;
            memcpy(out + w, rep, n);
            w += n;
        } else {
            if (w + 1 >= out_n) return 0;
            out[w++] = c;
        }
    }
    out[w] = '\0';
    return 1;
}

static int emit(ava_dk_ui_runtime_t *rt, const char *json)
{
    if (!rt || !rt->send_json || !json) return 0;
    rt->send_json(json, rt->send_user);
    return 1;
}

static void cancel_screen_timers(ava_dk_ui_runtime_t *rt, ava_dk_screen_id_t next)
{
    int i;
    if (!rt || next == rt->current) return;
    for (i = 0; i < AVA_DK_SCREEN_UNKNOWN; i++) {
        if (rt->screens[i].cancel_timers) {
            rt->screens[i].cancel_timers(rt->screens[i].user);
        }
    }
    for (i = 0; i < rt->custom_screen_count; i++) {
        if (rt->custom_screens[i].cancel_timers) {
            rt->custom_screens[i].cancel_timers(rt->custom_screens[i].user);
        }
    }
}

static int find_custom_screen(const ava_dk_ui_runtime_t *rt, const char *name)
{
    int i;
    if (!rt || !name) return -1;
    for (i = 0; i < rt->custom_screen_count; i++) {
        const char *screen_id = rt->custom_contracts[i].screen_id;
        if (screen_id && strcmp(screen_id, name) == 0) return i;
    }
    return -1;
}

static ava_dk_screen_vtable_t *current_screen_vtable(ava_dk_ui_runtime_t *rt)
{
    if (!rt) return NULL;
    if (rt->current == AVA_DK_SCREEN_UNKNOWN) {
        if (rt->current_custom_index >= 0 && rt->current_custom_index < rt->custom_screen_count) {
            return &rt->custom_screens[rt->current_custom_index];
        }
        return NULL;
    }
    if (rt->current < 0 || rt->current >= AVA_DK_SCREEN_UNKNOWN) return NULL;
    return &rt->screens[rt->current];
}

static const char *safe_str(const char *value)
{
    return value ? value : "";
}

static int json_str(const char *json, const char *key, char *out, size_t out_n)
{
    char needle[64];
    const char *p;
    if (!json || !key || !out || out_n == 0) return 0;
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(json, needle);
    if (!p) return 0;
    p += strlen(needle);
    while (*p == ' ' || *p == ':' || *p == '\t') p++;
    if (*p != '"') return 0;
    p++;
    return json_str_copy(p, out, out_n);
}

static int json_str_copy(const char *p, char *out, size_t out_n)
{
    size_t w = 0;
    while (*p && *p != '"') {
        if (*p == '\\' && p[1]) p++;
        if (w + 1 >= out_n) return 0;
        out[w++] = *p++;
    }
    if (*p != '"') return 0;
    out[w] = '\0';
    return 1;
}

static const char *json_data_ptr(const char *json, size_t *len)
{
    const char *p = strstr(json, "\"data\"");
    const char *start;
    char open;
    char close;
    int depth = 1;
    if (!len) return "{}";
    if (!p) { *len = 2; return "{}"; }
    p += 6;
    while (*p == ' ' || *p == ':') p++;
    if (*p != '{' && *p != '[') { *len = 2; return "{}"; }
    start = p;
    open = *p;
    close = (open == '{') ? '}' : ']';
    p++;
    while (*p && depth > 0) {
        if (*p == '"') {
            p++;
            while (*p && *p != '"') {
                if (*p == '\\') p++;
                if (*p) p++;
            }
            if (*p) p++;
            continue;
        }
        if (*p == open) depth++;
        if (*p == close) depth--;
        p++;
    }
    *len = (size_t)(p - start);
    return start;
}
