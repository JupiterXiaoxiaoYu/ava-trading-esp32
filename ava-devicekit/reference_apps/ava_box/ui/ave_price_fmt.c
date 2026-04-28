/**
 * @file ave_price_fmt.c
 */
#include "ave_price_fmt.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NORMAL_MAX_CHARS 8
#define SCI_SMALL_THRESHOLD 0.0001
#define SCI_LARGE_THRESHOLD 100000000.0

static void _fmt_money_normal(char *buf, size_t n, double value);
static void _fmt_sci(char *buf, size_t n, double value);

void ave_fmt_price(char *buf, size_t n, double price)
{
    _fmt_money_normal(buf, n, price);
}

static void _copy_price(char *buf, size_t n, const char *raw_price)
{
    if (!buf || n == 0) return;
    snprintf(buf, n, "%s", raw_price && raw_price[0] ? raw_price : "$0");
}

static void _trim_decimal(char *buf)
{
    char *dot;
    if (!buf) return;
    dot = strchr(buf, '.');
    if (!dot) return;
    char *end = buf + strlen(buf) - 1;
    while (end > dot && *end == '0') {
        *end = '\0';
        end--;
    }
    if (end == dot) *end = '\0';
    if (strcmp(buf, "-0") == 0) snprintf(buf, 3, "0");
}

static void _trim_exp_zeros(char *buf)
{
    char *e = strchr(buf, 'e');
    char *src;
    char *dst;
    if (!e || !e[1]) return;
    if (e[1] == '+') {
        memmove(e + 1, e + 2, strlen(e + 2) + 1);
    }
    src = e + 1;
    if (*src == '-') src++;
    dst = src;
    while (*src == '0' && src[1]) src++;
    if (src != dst) {
        memmove(dst, src, strlen(src) + 1);
    }
}

static void _fmt_sci(char *buf, size_t n, double value)
{
    if (!buf || n == 0) return;
    if (value == 0.0) {
        snprintf(buf, n, "0");
        return;
    }
    snprintf(buf, n, "%.2e", value);
    _trim_exp_zeros(buf);
}

static int _normal_decimals(double abs_value)
{
    if (abs_value >= 1000000.0) return 0;
    if (abs_value >= 1000.0) return 0;
    if (abs_value >= 100.0) return 1;
    if (abs_value >= 1.0) return 2;
    if (abs_value >= 0.01) return 4;
    return 6;
}

static void _fmt_plain_number(char *buf, size_t n, double value, int max_chars)
{
    char tmp[32] = {0};
    double abs_value;
    int decimals;

    if (!buf || n == 0) return;
    if (value == 0.0) {
        snprintf(buf, n, "0");
        return;
    }

    abs_value = value < 0 ? -value : value;
    if (abs_value < SCI_SMALL_THRESHOLD || abs_value >= SCI_LARGE_THRESHOLD) {
        _fmt_sci(buf, n, value);
        return;
    }

    decimals = _normal_decimals(abs_value);
    snprintf(tmp, sizeof(tmp), "%.*f", decimals, value);
    _trim_decimal(tmp);
    if ((int)strlen(tmp) <= max_chars) {
        snprintf(buf, n, "%s", tmp);
        return;
    }

    for (decimals = decimals - 1; decimals >= 0; decimals--) {
        snprintf(tmp, sizeof(tmp), "%.*f", decimals, value);
        _trim_decimal(tmp);
        if ((int)strlen(tmp) <= max_chars) {
            snprintf(buf, n, "%s", tmp);
            return;
        }
    }
    _fmt_sci(buf, n, value);
}

static void _fmt_money_normal(char *buf, size_t n, double value)
{
    char num[32] = {0};
    if (!buf || n == 0) return;
    if (value < 0) {
        _fmt_plain_number(num, sizeof(num), -value, NORMAL_MAX_CHARS);
        snprintf(buf, n, "-$%s", num);
    } else {
        _fmt_plain_number(num, sizeof(num), value, NORMAL_MAX_CHARS);
        snprintf(buf, n, "$%s", num);
    }
}

static void _fmt_money_compact(char *buf, size_t n, double value)
{
    static const struct {
        const char *suffix;
        double divisor;
    } units[] = {{"T", 1000000000000.0}, {"B", 1000000000.0}, {"M", 1000000.0}, {"K", 1000.0}};
    char num[32] = {0};
    double abs_value = value < 0 ? -value : value;
    const char *sign = value < 0 ? "-$" : "$";

    if (!buf || n == 0) return;
    for (size_t i = 0; i < sizeof(units) / sizeof(units[0]); i++) {
        if (abs_value >= units[i].divisor) {
            double scaled = abs_value / units[i].divisor;
            snprintf(num, sizeof(num), "%.1f", scaled);
            _trim_decimal(num);
            if ((int)(strlen(sign) + strlen(num) + strlen(units[i].suffix)) <= NORMAL_MAX_CHARS + 1) {
                snprintf(buf, n, "%s%s%s", sign, num, units[i].suffix);
                return;
            }
            snprintf(num, sizeof(num), "%.0f", scaled);
            if ((int)(strlen(sign) + strlen(num) + strlen(units[i].suffix)) <= NORMAL_MAX_CHARS + 1) {
                snprintf(buf, n, "%s%s%s", sign, num, units[i].suffix);
                return;
            }
            break;
        }
    }
    _fmt_money_normal(buf, n, value);
}

static const char *_numeric_start(const char *raw_price)
{
    if (!raw_price) return "";
    if (raw_price[0] == '-' && raw_price[1] == '$') return raw_price + 2;
    if (raw_price[0] == '$') return raw_price + 1;
    return raw_price;
}

void ave_fmt_price_text(char *buf, size_t n, const char *raw_price)
{
    char *end = NULL;
    double price;

    if (!buf || n == 0) return;
    if (!raw_price || !raw_price[0]) {
        snprintf(buf, n, "$0");
        return;
    }

    int neg_money = raw_price[0] == '-' && raw_price[1] == '$';
    const char *start = _numeric_start(raw_price);
    price = strtod(start, &end);
    if (end == start) {
        _copy_price(buf, n, raw_price);
        return;
    }
    if (neg_money) price = -price;

    while (*end == ' ') end++;
    if (*end != '\0') {
        _copy_price(buf, n, raw_price);
        return;
    }

    _fmt_money_normal(buf, n, price);
}

void ave_fmt_change(char *buf, size_t n, double pct)
{
    const char *sign = (pct >= 0) ? "▲ +" : "▼ ";
    double abs_pct = pct < 0 ? -pct : pct;
    char num[32] = {0};
    _fmt_plain_number(num, sizeof(num), abs_pct, 6);
    snprintf(buf, n, "%s%s%%", sign, num);
}

void ave_fmt_volume(char *buf, size_t n, double value)
{
    _fmt_money_compact(buf, n, value);
}

int16_t ave_price_to_chart(double price, double price_min, double price_max)
{
    if (price_min <= 0 || price_max <= 0 || price_min == price_max || price <= 0) {
        /* Linear fallback */
        if (price_max == price_min) return 500;
        double ratio = (price - price_min) / (price_max - price_min);
        if (ratio < 0) ratio = 0;
        if (ratio > 1) ratio = 1;
        return (int16_t)(ratio * 1000);
    }
    /* Log normalization */
    double log_min = log10(price_min);
    double log_max = log10(price_max);
    double log_val = log10(price > 0 ? price : price_min);
    double range = log_max - log_min;
    if (range <= 0) return 500;
    double ratio = (log_val - log_min) / range;
    if (ratio < 0) ratio = 0;
    if (ratio > 1) ratio = 1;
    return (int16_t)(ratio * 1000);
}
