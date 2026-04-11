/**
 * @file screen_portfolio.c
 * @brief PORTFOLIO screen — proxy wallet holdings with P&L.
 *
 * Layout (320×240 landscape):
 *   y=  0..22   top bar: "PORTFOLIO  $1,247  +4.1%"
 *   y= 22..38   header row (Symbol / Avg / Value / P&L)
 *   y= 38..200  holding rows (up to 6 visible, scrollable with UP/DOWN)
 *   y=200..215  total P&L summary
 *   y=215..240  bottom bar: [B] BACK  [X] SELL  [A] DETAIL  [Y] CHAIN
 */
#include "ave_screen_manager.h"
#include "ave_font_provider.h"
#include "ave_json_utils.h"
#include "ave_transport.h"
#if __has_include("lvgl.h")
#include "lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define MAX_HOLDINGS  20
#define ROW_H         28
#define HEADER_Y      22
#define HEADER_H      16
#define ROWS_Y        (HEADER_Y + HEADER_H)
#define SUMMARY_DIV_Y 202
#define SUMMARY_Y     205
#define BOTTOM_DIV_Y  217
#define BOTTOM_Y      217

#define COL_SYM_X     6
#define COL_SYM_W     74
#define COL_AVG_X     84
#define COL_AVG_W     72
#define COL_VAL_X     162
#define COL_VAL_W     72
#define COL_PNL_X     240
#define COL_PNL_W     74
#define COL_TEXT_Y    2
#define ROW_TEXT_Y    7

typedef struct {
    char symbol[24];
    char avg_cost_usd[20];
    char value_usd[20];
    char pnl[20];
    char pnl_pct[16];
    int  pnl_positive;   /* 1=green, 0=red, -1=neutral (null) */
    char addr[64];        /* token address */
    char chain[16];       /* chain name */
    char contract_tail[12];
    char source_tag[24];
    char balance_raw[96]; /* machine/raw balance string for sell quantity */
} holding_t;

static holding_t s_holdings[MAX_HOLDINGS];
static int       s_holding_count = 0;
static int       s_scroll_top    = 0;   /* index of first visible row */
static int       s_sel_idx       = 0;   /* selected row index (absolute) */
#define VISIBLE_ROWS  6

static lv_obj_t *s_screen      = NULL;
static lv_obj_t *s_lbl_title   = NULL;
static lv_obj_t *s_lbl_total   = NULL;
static lv_obj_t *s_lbl_pnl     = NULL;
static lv_obj_t *s_lbl_summary = NULL;
static lv_timer_t *s_back_timer = NULL;

void screen_portfolio_cancel_back_timer(void)
{
    if (s_back_timer) {
        lv_timer_del(s_back_timer);
        s_back_timer = NULL;
    }
}

/* Row containers and labels [row][col]:  0=symbol, 1=avg, 2=value, 3=pnl */
static lv_obj_t *s_row_bg[VISIBLE_ROWS];
static lv_obj_t *s_row_sym[VISIBLE_ROWS];
static lv_obj_t *s_row_avg[VISIBLE_ROWS];
static lv_obj_t *s_row_val[VISIBLE_ROWS];
static lv_obj_t *s_row_pnl[VISIBLE_ROWS];

#define COLOR_GREEN   lv_color_hex(0x00C853)
#define COLOR_RED     lv_color_hex(0xFF1744)
#define COLOR_ORANGE  lv_color_hex(0xFF6D00)
#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)
#define COLOR_SOL     lv_color_hex(0x9945FF)
#define COLOR_ETH     lv_color_hex(0x627EEA)
#define COLOR_BSC     lv_color_hex(0xF3BA2F)
#define COLOR_BASE    lv_color_hex(0x0052FF)
#define COLOR_BG      lv_color_hex(0x0A0A0A)
#define COLOR_BAR     lv_color_hex(0x141414)
#define COLOR_ROW_ALT lv_color_hex(0x111111)
#define COLOR_DIVIDER lv_color_hex(0x2A2A2A)
#define COLOR_HDR     lv_color_hex(0x1E1E1E)

/* ─── JSON helpers ───────────────────────────────────────────────────────── */
static int _str(const char *o, const char *k, char *out, int n) {
    char nd[64]; snprintf(nd, sizeof(nd), "\"%s\"", k);
    const char *p = strstr(o, nd); if (!p) return 0;
    p += strlen(nd);
    while (*p == ' ' || *p == ':') p++;
    if (*p != '"') return 0;
    return ave_json_decode_quoted(p, out, (size_t)n, NULL);
}

/* Parse machine/raw amount as a plain quoted string and fail closed if it would
 * overflow destination storage. JSON escapes are rejected intentionally here:
 * sell quantities are machine fields and should arrive as plain decimals. */
static int _machine_raw_exact(const char *o, const char *k, char *out, int n)
{
    char nd[64];
    const char *p = NULL;
    const char *q = NULL;
    size_t len = 0;

    if (!o || !k || !out || n <= 1) return 0;
    snprintf(nd, sizeof(nd), "\"%s\"", k);
    p = strstr(o, nd);
    if (!p) return 0;
    p += strlen(nd);
    while (*p == ' ' || *p == ':') p++;
    if (*p != '"') return 0;

    q = p + 1;
    while (*q) {
        if (*q == '\\') return 0;
        if (*q == '"') break;
        q++;
    }
    if (*q != '"') return 0;

    len = (size_t)(q - (p + 1));
    if (len == 0 || len >= (size_t)n) return 0;

    memcpy(out, p + 1, len);
    out[len] = '\0';
    return 1;
}

static const char *_chain_hex(const char *chain)
{
    if (!chain || !chain[0]) return NULL;
    if (strncmp(chain, "solana", 6) == 0 || strcmp(chain, "SOL") == 0) return "9945FF";
    if (strncmp(chain, "eth", 3) == 0 || strcmp(chain, "ETH") == 0) return "627EEA";
    if (strncmp(chain, "bsc", 3) == 0 || strcmp(chain, "BSC") == 0) return "F3BA2F";
    if (strncmp(chain, "base", 4) == 0 || strcmp(chain, "BASE") == 0) return "0052FF";
    return NULL;
}

static void _set_portfolio_title(const char *mode_label, const char *chain_label)
{
    char title_buf[64];
    const char *base_title =
        (mode_label && strcmp(mode_label, "PAPER") == 0) ? "PAPER PORT" : "PORTFOLIO";

    if (!s_lbl_title) return;

    if (chain_label && chain_label[0] && _chain_hex(chain_label)) {
        snprintf(title_buf, sizeof(title_buf), "%s %s", base_title, chain_label);
        lv_label_set_text(s_lbl_title, title_buf);
        return;
    }

    lv_label_set_text(s_lbl_title, base_title);
}

/* Like _str(), but only matches keys at the shallow object level of the payload.
 * This prevents accidentally reading holding-level fields (e.g. first row pnl_pct)
 * into the portfolio summary when top-level fields are absent. */
static const char *_match_brace(const char *p, const char *end)
{
    int depth = 0;
    int in_str = 0;
    int esc = 0;
    for (const char *q = p; q < end && *q; q++) {
        char c = *q;
        if (in_str) {
            if (esc) { esc = 0; continue; }
            if (c == '\\') { esc = 1; continue; }
            if (c == '"') in_str = 0;
            continue;
        }
        if (c == '"') { in_str = 1; continue; }
        if (c == '{') depth++;
        else if (c == '}') {
            depth--;
            if (depth == 0) return q + 1; /* end is exclusive */
        }
    }
    return NULL;
}

static int _str_shallow_object(const char *obj_start, const char *obj_end,
                               const char *k, char *out, int n)
{
    if (!obj_start || !obj_end || obj_end <= obj_start) return 0;
    size_t klen = strlen(k);

    int obj_depth = 0;
    int arr_depth = 0;

    /* p is advanced manually so we can skip over JSON strings efficiently. */
    for (const char *p = obj_start; p < obj_end && *p; ) {
        char c = *p;
        if (c == '"') {
            /* Keys are quoted; only match at depth=1 and outside arrays. */
            if (obj_depth == 1 && arr_depth == 0) {
                const char *key = p + 1;
                if (key + klen + 1 < obj_end &&
                    memcmp(key, k, klen) == 0 &&
                    key[klen] == '"') {
                    const char *q = key + klen + 1;
                    while (q < obj_end && (*q == ' ' || *q == '\n' || *q == '\r' || *q == '\t')) q++;
                    if (q < obj_end && *q == ':') {
                        q++;
                        while (q < obj_end && (*q == ' ' || *q == '\n' || *q == '\r' || *q == '\t')) q++;
                        if (q < obj_end && *q == '"')
                            return ave_json_decode_quoted(q, out, (size_t)n, NULL);
                        /* Treat null/non-string as absent for this screen. */
                        return 0;
                    }
                }
            }

            /* Skip over any JSON string literal (key or value). */
            p++; /* after opening quote */
            int esc = 0;
            while (p < obj_end && *p) {
                if (esc) { esc = 0; p++; continue; }
                if (*p == '\\') { esc = 1; p++; continue; }
                if (*p == '"') { p++; break; }
                p++;
            }
            continue;
        }

        if (c == '{') obj_depth++;
        else if (c == '}') obj_depth--;
        else if (c == '[') arr_depth++;
        else if (c == ']') arr_depth--;
        p++;
    }
    return 0;
}

static int _str_portfolio_top_level(const char *json, const char *k, char *out, int n)
{
    if (!json) return 0;
    const char *end = json + strlen(json);

    /* Try to scope to the {"data":{...}} object if present. */
    const char *scope_start = json;
    const char *scope_end = end;
    const char *data = strstr(json, "\"data\"");
    if (data) {
        const char *brace = strchr(data, '{');
        if (brace) {
            const char *brace_end = _match_brace(brace, end);
            if (brace_end) {
                scope_start = brace;
                scope_end = brace_end;
            }
        }
    }
    return _str_shallow_object(scope_start, scope_end, k, out, n);
}

static int _int_shallow_object(const char *obj_start, const char *obj_end,
                               const char *k, int *out)
{
    if (!obj_start || !obj_end || obj_end <= obj_start || !k || !out) return 0;
    size_t klen = strlen(k);
    int obj_depth = 0;
    int arr_depth = 0;

    for (const char *p = obj_start; p < obj_end && *p; ) {
        char c = *p;
        if (c == '"') {
            if (obj_depth == 1 && arr_depth == 0) {
                const char *key = p + 1;
                if (key + klen + 1 < obj_end &&
                    memcmp(key, k, klen) == 0 &&
                    key[klen] == '"') {
                    const char *q = key + klen + 1;
                    while (q < obj_end && (*q == ' ' || *q == '\n' || *q == '\r' || *q == '\t')) q++;
                    if (q < obj_end && *q == ':') {
                        char *endptr = NULL;
                        long parsed = 0;
                        q++;
                        while (q < obj_end && (*q == ' ' || *q == '\n' || *q == '\r' || *q == '\t')) q++;
                        if (q >= obj_end) return 0;
                        parsed = strtol(q, &endptr, 10);
                        if (!endptr || endptr == q || endptr > obj_end) return 0;
                        *out = (int)parsed;
                        return 1;
                    }
                }
            }

            p++;
            int esc = 0;
            while (p < obj_end && *p) {
                if (esc) { esc = 0; p++; continue; }
                if (*p == '\\') { esc = 1; p++; continue; }
                if (*p == '"') { p++; break; }
                p++;
            }
            continue;
        }

        if (c == '{') obj_depth++;
        else if (c == '}') obj_depth--;
        else if (c == '[') arr_depth++;
        else if (c == ']') arr_depth--;
        p++;
    }
    return 0;
}

static int _int_portfolio_top_level(const char *json, const char *k, int *out)
{
    if (!json) return 0;
    const char *end = json + strlen(json);

    const char *scope_start = json;
    const char *scope_end = end;
    const char *data = strstr(json, "\"data\"");
    if (data) {
        const char *brace = strchr(data, '{');
        if (brace) {
            const char *brace_end = _match_brace(brace, end);
            if (brace_end) {
                scope_start = brace;
                scope_end = brace_end;
            }
        }
    }
    return _int_shallow_object(scope_start, scope_end, k, out);
}

static int _bool(const char *o, const char *k, int def) {
    char nd[64]; snprintf(nd, sizeof(nd), "\"%s\"", k);
    const char *p = strstr(o, nd); if (!p) return def;
    p += strlen(nd);
    while (*p == ' ' || *p == ':') p++;
    if (*p == 't') return 1;
    if (*p == 'f') return 0;
    if (*p == 'n') return -1;  /* null */
    return def;
}

static int _is_empty_payload(const char *json)
{
    return (!json || strcmp(json, "{}") == 0);
}

static void _compact_upper_tag(const char *src, char *out, size_t out_n, int max_chars)
{
    int written = 0;

    if (!out || out_n == 0) return;
    out[0] = '\0';
    if (!src || !src[0] || max_chars <= 0) return;

    while (*src && written < max_chars && (size_t)written < out_n - 1) {
        char c = *src++;
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) {
            if (c >= 'a' && c <= 'z') c = (char)(c - ('a' - 'A'));
            out[written++] = c;
        }
    }
    out[written] = '\0';
}

static void _parse(const char *json) {
    s_holding_count = 0;
    s_scroll_top    = 0;
    s_sel_idx       = 0;
    memset(s_holdings, 0, sizeof(s_holdings));

    /* Find "holdings" array */
    const char *arr = strstr(json, "\"holdings\"");
    if (!arr) return;
    arr = strchr(arr, '['); if (!arr) return;
    arr++;

    const char *p = arr;
    while (*p && s_holding_count < MAX_HOLDINGS) {
        p = strchr(p, '{'); if (!p) break;
        int depth = 1;
        const char *start = p++;
        while (*p && depth > 0) {
            if (*p == '{') depth++;
            if (*p == '}') depth--;
            p++;
        }
        size_t len = (size_t)(p - start);
        char *obj = malloc(len + 1);
        if (!obj) break;
        memcpy(obj, start, len); obj[len] = 0;

        holding_t *h = &s_holdings[s_holding_count];
        memset(h, 0, sizeof(*h));
        _str(obj, "symbol",      h->symbol,      sizeof(h->symbol));
        _str(obj, "avg_cost_usd", h->avg_cost_usd, sizeof(h->avg_cost_usd));
        _str(obj, "value_usd",   h->value_usd,   sizeof(h->value_usd));
        _str(obj, "pnl",         h->pnl,         sizeof(h->pnl));
        _str(obj, "pnl_pct",     h->pnl_pct,     sizeof(h->pnl_pct));
        h->pnl_positive = _bool(obj, "pnl_positive", -1);
        _str(obj, "addr",        h->addr,        sizeof(h->addr));
        _str(obj, "chain",       h->chain,       sizeof(h->chain));
        _str(obj, "contract_tail", h->contract_tail, sizeof(h->contract_tail));
        _str(obj, "source_tag",  h->source_tag,  sizeof(h->source_tag));
        /* accept either "balance_raw" or "amount_raw", but fail closed on truncation */
        if (!_machine_raw_exact(obj, "balance_raw", h->balance_raw, sizeof(h->balance_raw)))
            _machine_raw_exact(obj, "amount_raw", h->balance_raw, sizeof(h->balance_raw));

        if (h->symbol[0] == 0) {
            free(obj);
            continue;
        }

        free(obj);
        s_holding_count++;
    }
}

/* ─── Refresh visible rows ───────────────────────────────────────────────── */
static void _refresh_rows(void) {
    for (int i = 0; i < VISIBLE_ROWS; i++) {
        int idx = s_scroll_top + i;
        int is_sel = (idx == s_sel_idx);
        if (idx < s_holding_count) {
            holding_t *h = &s_holdings[idx];
            char sym_buf[64];
            char source_tag[8];
            _compact_upper_tag(h->source_tag, source_tag, sizeof(source_tag), 4);
            if (h->contract_tail[0] && source_tag[0]) {
                snprintf(sym_buf, sizeof(sym_buf), "%s %s *%s",
                         h->symbol, source_tag, h->contract_tail);
            } else if (source_tag[0]) {
                snprintf(sym_buf, sizeof(sym_buf), "%s %s",
                         h->symbol, source_tag);
            } else if (h->contract_tail[0]) {
                snprintf(sym_buf, sizeof(sym_buf), "%s *%s", h->symbol, h->contract_tail);
            } else {
                snprintf(sym_buf, sizeof(sym_buf), "%s", h->symbol);
            }
            lv_label_set_text(s_row_sym[i], sym_buf);
            lv_label_set_text(s_row_avg[i], h->avg_cost_usd[0] ? h->avg_cost_usd : "N/A");
            lv_label_set_text(s_row_val[i], h->value_usd[0] ? h->value_usd : "--");
            lv_label_set_text(s_row_pnl[i], h->pnl[0] ? h->pnl : "N/A");
            lv_color_t pnl_color;
            if      (h->pnl_positive == 1)  pnl_color = COLOR_GREEN;
            else if (h->pnl_positive == 0)  pnl_color = COLOR_RED;
            else                             pnl_color = COLOR_GRAY;
            lv_obj_set_style_text_color(s_row_pnl[i], pnl_color, 0);
            lv_obj_clear_flag(s_row_sym[i], LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(s_row_avg[i], LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(s_row_val[i], LV_OBJ_FLAG_HIDDEN);
            lv_obj_clear_flag(s_row_pnl[i], LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_label_set_text(s_row_sym[i], "");
            lv_label_set_text(s_row_avg[i], "");
            lv_label_set_text(s_row_val[i], "");
            lv_label_set_text(s_row_pnl[i], "");
            lv_obj_set_style_bg_color(s_row_bg[i], (i % 2 == 0) ? COLOR_BG : COLOR_ROW_ALT, 0);
            lv_obj_set_style_border_width(s_row_bg[i], 0, 0);
        }
        /* Selection highlight */
        if (is_sel && idx < s_holding_count) {
            lv_obj_set_style_bg_color(s_row_bg[i], lv_color_hex(0x1A1A2E), 0);
            lv_obj_set_style_border_color(s_row_bg[i], lv_color_hex(0xFF6D00), 0);
            lv_obj_set_style_border_width(s_row_bg[i], 2, 0);
            lv_obj_set_style_border_side(s_row_bg[i], LV_BORDER_SIDE_LEFT, 0);
        } else {
            lv_color_t bg = (i % 2 == 0) ? COLOR_BG : COLOR_ROW_ALT;
            lv_obj_set_style_bg_color(s_row_bg[i], bg, 0);
            lv_obj_set_style_border_width(s_row_bg[i], 0, 0);
        }
    }
}

/* ─── Back fallback ──────────────────────────────────────────────────────── */
static void _back_timeout_cb(lv_timer_t *t)
{
    (void)t;
    s_back_timer = NULL;
    ave_sm_go_to_feed();  /* server didn't respond, navigate locally */
}

/* ─── Build screen ───────────────────────────────────────────────────────── */
static void _build(void) {
    s_screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_screen, COLOR_BG, 0);
    lv_obj_set_size(s_screen, 320, 240);

    /* Top bar */
    lv_obj_t *top = lv_obj_create(s_screen);
    lv_obj_set_size(top, 320, 22);
    lv_obj_align(top, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_set_style_bg_color(top, COLOR_BAR, 0);
    lv_obj_set_style_border_width(top, 0, 0);
    lv_obj_set_style_pad_all(top, 0, 0);

    s_lbl_title = lv_label_create(top);
    lv_obj_align(s_lbl_title, LV_ALIGN_LEFT_MID, 6, 0);
    lv_label_set_text(s_lbl_title, "PORTFOLIO");
    lv_obj_set_style_text_color(s_lbl_title, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_title, &lv_font_montserrat_12, 0);

    s_lbl_total = lv_label_create(top);
    lv_obj_align(s_lbl_total, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_color(s_lbl_total, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_total, &lv_font_montserrat_12, 0);

    s_lbl_pnl = lv_label_create(top);
    lv_obj_align(s_lbl_pnl, LV_ALIGN_RIGHT_MID, -6, 0);
    lv_obj_set_style_text_font(s_lbl_pnl, &lv_font_montserrat_12, 0);

    /* Column header row */
    lv_obj_t *hdr = lv_obj_create(s_screen);
    lv_obj_set_size(hdr, 320, HEADER_H);
    lv_obj_align(hdr, LV_ALIGN_TOP_LEFT, 0, HEADER_Y);
    lv_obj_set_style_bg_color(hdr, COLOR_HDR, 0);
    lv_obj_set_style_border_width(hdr, 0, 0);
    lv_obj_set_style_pad_all(hdr, 0, 0);

    lv_obj_t *hdr_sym = lv_label_create(hdr);
    lv_obj_set_pos(hdr_sym, COL_SYM_X, COL_TEXT_Y);
    lv_obj_set_width(hdr_sym, COL_SYM_W);
    lv_label_set_long_mode(hdr_sym, LV_LABEL_LONG_CLIP);
    lv_label_set_text(hdr_sym, "Symbol");
    lv_obj_set_style_text_color(hdr_sym, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(hdr_sym, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(hdr_sym, LV_TEXT_ALIGN_LEFT, 0);

    lv_obj_t *hdr_avg = lv_label_create(hdr);
    lv_obj_set_pos(hdr_avg, COL_AVG_X, COL_TEXT_Y);
    lv_obj_set_width(hdr_avg, COL_AVG_W);
    lv_label_set_long_mode(hdr_avg, LV_LABEL_LONG_CLIP);
    lv_label_set_text(hdr_avg, "Avg");
    lv_obj_set_style_text_color(hdr_avg, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(hdr_avg, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(hdr_avg, LV_TEXT_ALIGN_RIGHT, 0);

    lv_obj_t *hdr_val = lv_label_create(hdr);
    lv_obj_set_pos(hdr_val, COL_VAL_X, COL_TEXT_Y);
    lv_obj_set_width(hdr_val, COL_VAL_W);
    lv_label_set_long_mode(hdr_val, LV_LABEL_LONG_CLIP);
    lv_label_set_text(hdr_val, "Value");
    lv_obj_set_style_text_color(hdr_val, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(hdr_val, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(hdr_val, LV_TEXT_ALIGN_RIGHT, 0);

    lv_obj_t *hdr_pnl = lv_label_create(hdr);
    lv_obj_set_pos(hdr_pnl, COL_PNL_X, COL_TEXT_Y);
    lv_obj_set_width(hdr_pnl, COL_PNL_W);
    lv_label_set_long_mode(hdr_pnl, LV_LABEL_LONG_CLIP);
    lv_label_set_text(hdr_pnl, "P&L");
    lv_obj_set_style_text_color(hdr_pnl, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(hdr_pnl, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(hdr_pnl, LV_TEXT_ALIGN_RIGHT, 0);

    /* Holding rows */
    for (int i = 0; i < VISIBLE_ROWS; i++) {
        int y = ROWS_Y + i * ROW_H;
        lv_color_t bg = (i % 2 == 0) ? COLOR_BG : COLOR_ROW_ALT;

        s_row_bg[i] = lv_obj_create(s_screen);
        lv_obj_set_size(s_row_bg[i], 320, ROW_H);
        lv_obj_align(s_row_bg[i], LV_ALIGN_TOP_LEFT, 0, y);
        lv_obj_set_style_bg_color(s_row_bg[i], bg, 0);
        lv_obj_set_style_border_width(s_row_bg[i], 0, 0);
        lv_obj_set_style_pad_all(s_row_bg[i], 0, 0);

        s_row_sym[i] = lv_label_create(s_row_bg[i]);
        lv_obj_set_pos(s_row_sym[i], COL_SYM_X, ROW_TEXT_Y);
        lv_obj_set_width(s_row_sym[i], COL_SYM_W);
        lv_label_set_long_mode(s_row_sym[i], LV_LABEL_LONG_CLIP);
        lv_obj_set_style_text_color(s_row_sym[i], COLOR_WHITE, 0);
        lv_obj_set_style_text_font(s_row_sym[i], ave_font_cjk_14(), 0);
        lv_obj_set_style_text_align(s_row_sym[i], LV_TEXT_ALIGN_LEFT, 0);

        s_row_avg[i] = lv_label_create(s_row_bg[i]);
        lv_obj_set_pos(s_row_avg[i], COL_AVG_X, ROW_TEXT_Y);
        lv_obj_set_width(s_row_avg[i], COL_AVG_W);
        lv_label_set_long_mode(s_row_avg[i], LV_LABEL_LONG_CLIP);
        lv_obj_set_style_text_color(s_row_avg[i], COLOR_WHITE, 0);
        lv_obj_set_style_text_font(s_row_avg[i], &lv_font_montserrat_12, 0);
        lv_obj_set_style_text_align(s_row_avg[i], LV_TEXT_ALIGN_RIGHT, 0);

        s_row_val[i] = lv_label_create(s_row_bg[i]);
        lv_obj_set_pos(s_row_val[i], COL_VAL_X, ROW_TEXT_Y);
        lv_obj_set_width(s_row_val[i], COL_VAL_W);
        lv_label_set_long_mode(s_row_val[i], LV_LABEL_LONG_CLIP);
        lv_obj_set_style_text_color(s_row_val[i], COLOR_WHITE, 0);
        lv_obj_set_style_text_font(s_row_val[i], &lv_font_montserrat_12, 0);
        lv_obj_set_style_text_align(s_row_val[i], LV_TEXT_ALIGN_RIGHT, 0);

        s_row_pnl[i] = lv_label_create(s_row_bg[i]);
        lv_obj_set_pos(s_row_pnl[i], COL_PNL_X, ROW_TEXT_Y);
        lv_obj_set_width(s_row_pnl[i], COL_PNL_W);
        lv_label_set_long_mode(s_row_pnl[i], LV_LABEL_LONG_CLIP);
        lv_obj_set_style_text_font(s_row_pnl[i], &lv_font_montserrat_12, 0);
        lv_obj_set_style_text_align(s_row_pnl[i], LV_TEXT_ALIGN_RIGHT, 0);
    }

    /* Summary bar */
    lv_obj_t *div = lv_obj_create(s_screen);
    lv_obj_set_size(div, 320, 1);
    lv_obj_align(div, LV_ALIGN_TOP_LEFT, 0, SUMMARY_DIV_Y);
    lv_obj_set_style_bg_color(div, COLOR_DIVIDER, 0);
    lv_obj_set_style_border_width(div, 0, 0);

    s_lbl_summary = lv_label_create(s_screen);
    lv_obj_align(s_lbl_summary, LV_ALIGN_TOP_LEFT, 6, SUMMARY_Y);
    lv_obj_set_width(s_lbl_summary, 308);
    lv_label_set_long_mode(s_lbl_summary, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_summary, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_summary, &lv_font_montserrat_12, 0);

    /* Bottom divider */
    lv_obj_t *div2 = lv_obj_create(s_screen);
    lv_obj_set_size(div2, 320, 1);
    lv_obj_align(div2, LV_ALIGN_TOP_LEFT, 0, BOTTOM_DIV_Y);
    lv_obj_set_style_bg_color(div2, COLOR_DIVIDER, 0);
    lv_obj_set_style_border_width(div2, 0, 0);

    /* ── Bottom bar affordances (Task 5) ─────────────────────────────── */
    lv_obj_t *bot = lv_obj_create(s_screen);
    lv_obj_set_size(bot, 320, 240 - BOTTOM_Y);
    lv_obj_set_pos(bot, 0, BOTTOM_Y);
    lv_obj_set_style_bg_opa(bot, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(bot, 0, 0);
    lv_obj_set_style_pad_all(bot, 0, 0);
    lv_obj_clear_flag(bot, LV_OBJ_FLAG_SCROLLABLE);

    /* Portfolio keeps Y for local chain cycling while preserving B/X/A actions. */
    lv_obj_t *slot_b = lv_obj_create(bot);
    lv_obj_set_size(slot_b, 64, 240 - BOTTOM_Y);
    lv_obj_set_pos(slot_b, 0, 0);
    lv_obj_set_style_bg_opa(slot_b, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_b, 0, 0);
    lv_obj_set_style_pad_all(slot_b, 0, 0);
    lv_obj_clear_flag(slot_b, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *slot_x = lv_obj_create(bot);
    lv_obj_set_size(slot_x, 64, 240 - BOTTOM_Y);
    lv_obj_set_pos(slot_x, 64, 0);
    lv_obj_set_style_bg_opa(slot_x, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_x, 0, 0);
    lv_obj_set_style_pad_all(slot_x, 0, 0);
    lv_obj_clear_flag(slot_x, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *slot_a = lv_obj_create(bot);
    lv_obj_set_size(slot_a, 64, 240 - BOTTOM_Y);
    lv_obj_set_pos(slot_a, 128, 0);
    lv_obj_set_style_bg_opa(slot_a, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_a, 0, 0);
    lv_obj_set_style_pad_all(slot_a, 0, 0);
    lv_obj_clear_flag(slot_a, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *slot_y = lv_obj_create(bot);
    lv_obj_set_size(slot_y, 128, 240 - BOTTOM_Y);
    lv_obj_set_pos(slot_y, 192, 0);
    lv_obj_set_style_bg_opa(slot_y, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_y, 0, 0);
    lv_obj_set_style_pad_all(slot_y, 0, 0);
    lv_obj_clear_flag(slot_y, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *lbl_back = lv_label_create(slot_b);
    lv_obj_align(lbl_back, LV_ALIGN_CENTER, 0, 0);
    lv_label_set_text(lbl_back, "[B] BACK");
    lv_obj_set_style_text_color(lbl_back, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(lbl_back, &lv_font_montserrat_12, 0);

    lv_obj_t *lbl_sell = lv_label_create(slot_x);
    lv_obj_align(lbl_sell, LV_ALIGN_CENTER, 0, 0);
    lv_label_set_text(lbl_sell, "[X] SELL");
    lv_obj_set_style_text_color(lbl_sell, COLOR_ORANGE, 0);
    lv_obj_set_style_text_font(lbl_sell, &lv_font_montserrat_12, 0);

    lv_obj_t *lbl_detail = lv_label_create(slot_a);
    lv_obj_align(lbl_detail, LV_ALIGN_CENTER, 0, 0);
    lv_label_set_text(lbl_detail, "[A] DETAIL");
    lv_obj_set_style_text_color(lbl_detail, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(lbl_detail, &lv_font_montserrat_12, 0);

    lv_obj_t *lbl_chain = lv_label_create(slot_y);
    lv_obj_align(lbl_chain, LV_ALIGN_CENTER, 0, 0);
    lv_label_set_text(lbl_chain, "[Y] CHAIN");
    lv_obj_set_style_text_color(lbl_chain, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(lbl_chain, &lv_font_montserrat_12, 0);
}

/* ─── Public API ──────────────────────────────────────────────────────────── */

void screen_portfolio_show(const char *json_data)
{
    screen_portfolio_cancel_back_timer();
    if (!s_screen) _build();
    lv_screen_load(s_screen);

    if (_is_empty_payload(json_data)) {
        s_holding_count = 0;
        s_scroll_top = 0;
        s_sel_idx = 0;
        memset(s_holdings, 0, sizeof(s_holdings));
        lv_label_set_text(s_lbl_total, "--");
        lv_label_set_text(s_lbl_pnl, "N/A");
        lv_obj_set_style_text_color(s_lbl_pnl, COLOR_GRAY, 0);
        lv_label_set_text(s_lbl_summary, "P&L: N/A (N/A)");
        _refresh_rows();
        return;
    }

    _parse(json_data);
    if (s_holding_count > 0) {
        int cursor = 0;
        if (_int_portfolio_top_level(json_data, "cursor", &cursor)) {
            if (cursor < 0) cursor = 0;
            if (cursor >= s_holding_count) cursor = s_holding_count - 1;
            s_sel_idx = cursor;
            s_scroll_top = (s_sel_idx >= VISIBLE_ROWS) ? (s_sel_idx - VISIBLE_ROWS + 1) : 0;
        }
    }

    /* Update top bar */
    char total[24] = {0}, pnl[20] = {0}, pnl_pct[16] = {0};
    char pnl_reason[48] = {0};
    char mode_label[16] = {0};
    char chain_label[8] = {0};
    _str_portfolio_top_level(json_data, "total_usd", total, sizeof(total));
    _str_portfolio_top_level(json_data, "pnl",       pnl,   sizeof(pnl));
    _str_portfolio_top_level(json_data, "pnl_pct",   pnl_pct, sizeof(pnl_pct));
    _str_portfolio_top_level(json_data, "pnl_reason", pnl_reason, sizeof(pnl_reason));
    _str_portfolio_top_level(json_data, "mode_label", mode_label, sizeof(mode_label));
    _str_portfolio_top_level(json_data, "chain_label", chain_label, sizeof(chain_label));

    _set_portfolio_title(mode_label, chain_label);

    lv_label_set_text(s_lbl_total, total[0] ? total : "--");

    if (pnl[0]) {
        const char *pnl_display = pnl;
        lv_label_set_text(s_lbl_pnl, pnl_display);
        lv_color_t pnl_color = COLOR_GRAY;
        if (pnl_display[0] == '+') pnl_color = COLOR_GREEN;
        else if (pnl_display[0] == '-') pnl_color = COLOR_RED;
        lv_obj_set_style_text_color(s_lbl_pnl, pnl_color, 0);
    } else {
        /* Frozen policy: missing portfolio-level P&L is neutral N/A (not blank). */
        lv_label_set_text(s_lbl_pnl, "N/A");
        lv_obj_set_style_text_color(s_lbl_pnl, COLOR_GRAY, 0);
    }

    /* Summary */
    char sum_buf[128];
    if (pnl_reason[0]) {
        if (strcmp(pnl_reason, "Cost basis unavailable") == 0) {
            snprintf(sum_buf, sizeof(sum_buf), "P&L summary unavailable");
        } else {
            snprintf(sum_buf, sizeof(sum_buf), "%s", pnl_reason);
        }
    } else {
        if (pnl_pct[0]) {
            snprintf(sum_buf, sizeof(sum_buf), "P&L: %s | ROI %s",
                     pnl[0] ? pnl : "N/A", pnl_pct);
        } else {
            snprintf(sum_buf, sizeof(sum_buf), "P&L: %s",
                     pnl[0] ? pnl : "N/A");
        }
    }
    lv_label_set_text(s_lbl_summary, sum_buf);

    _refresh_rows();
}

#if defined(VERIFY_PORTFOLIO)
/* Verification-only accessors for json_verify_include/lvgl stubs in tests. */
lv_obj_t *screen_portfolio__verify_get_top_pnl_label(void) { return s_lbl_pnl; }
lv_obj_t *screen_portfolio__verify_get_summary_label(void) { return s_lbl_summary; }
#endif

void screen_portfolio_key(int key)
{
    if (key == AVE_KEY_B) {
        screen_portfolio_cancel_back_timer();
        s_back_timer = lv_timer_create(_back_timeout_cb, 3000, NULL);
        lv_timer_set_repeat_count(s_back_timer, 1);
        ave_send_json("{\"type\":\"key_action\",\"action\":\"back\"}");
    } else if (key == AVE_KEY_UP) {
        if (s_sel_idx > 0) {
            s_sel_idx--;
            /* scroll up if selection moved above visible window */
            if (s_sel_idx < s_scroll_top) s_scroll_top = s_sel_idx;
            _refresh_rows();
        }
    } else if (key == AVE_KEY_DOWN) {
        if (s_sel_idx < s_holding_count - 1) {
            s_sel_idx++;
            /* scroll down if selection moved below visible window */
            if (s_sel_idx >= s_scroll_top + VISIBLE_ROWS)
                s_scroll_top = s_sel_idx - VISIBLE_ROWS + 1;
            _refresh_rows();
        }
    } else if (key == AVE_KEY_A) {
        if (s_holding_count < 1 || s_sel_idx < 0 || s_sel_idx >= s_holding_count) return;
        const holding_t *h = &s_holdings[s_sel_idx];
        if (h->addr[0] == '\0' || h->chain[0] == '\0') return; /* no actionable identity, ignore */
        char msg[384];
        ave_sm_json_field_t fields[] = {
            {"token_id", h->addr},
            {"chain", h->chain},
        };
        if (!ave_sm_build_key_action_json("portfolio_watch", fields, 2, msg, sizeof(msg))) return;
        ave_send_json(msg);
    } else if (key == AVE_KEY_X) {
        if (s_holding_count < 1 || s_sel_idx < 0 || s_sel_idx >= s_holding_count) return;
        const holding_t *hx = &s_holdings[s_sel_idx];
        if (hx->addr[0] == '\0' || hx->chain[0] == '\0' || hx->balance_raw[0] == '\0') return;
        char msg[512];
        ave_sm_json_field_t fields[] = {
            {"addr", hx->addr},
            {"chain", hx->chain},
            {"symbol", hx->symbol},
            {"balance_raw", hx->balance_raw},
        };
        if (!ave_sm_build_key_action_json("portfolio_sell", fields, 4, msg, sizeof(msg))) return;
        ave_send_json(msg);
    } else if (key == AVE_KEY_Y) {
        ave_send_json("{\"type\":\"key_action\",\"action\":\"portfolio_chain_cycle\"}");
    }
}

int screen_portfolio_get_selected_context_json(char *out, size_t out_n)
{
    char addr_esc[256];
    char chain_esc[64];
    char symbol_esc[64];

    if (!out || out_n == 0) return 0;
    if (s_holding_count < 1 || s_sel_idx < 0 || s_sel_idx >= s_holding_count) return 0;

    const holding_t *h = &s_holdings[s_sel_idx];
    if (!h->addr[0]) return 0;
    if (!h->chain[0]) return 0;
    if (!ave_sm_json_escape_string(h->addr, addr_esc, sizeof(addr_esc))) return 0;
    if (!ave_sm_json_escape_string(h->chain, chain_esc, sizeof(chain_esc))) return 0;
    if (!ave_sm_json_escape_string(h->symbol, symbol_esc, sizeof(symbol_esc))) return 0;

    int n = snprintf(
        out, out_n,
        "{\"screen\":\"portfolio\",\"cursor\":%d,\"token\":{\"addr\":\"%s\",\"chain\":\"%s\",\"symbol\":\"%s\"}}",
        s_sel_idx,
        addr_esc,
        chain_esc,
        symbol_esc
    );
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}
