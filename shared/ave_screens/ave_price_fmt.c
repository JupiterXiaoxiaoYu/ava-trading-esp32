/**
 * @file ave_price_fmt.c
 */
#include "ave_price_fmt.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void _fmt_money_sci(char *buf, size_t n, double value);

void ave_fmt_price(char *buf, size_t n, double price)
{
    _fmt_money_sci(buf, n, price);
}

static void _copy_price(char *buf, size_t n, const char *raw_price)
{
    if (!buf || n == 0) return;
    snprintf(buf, n, "%s", raw_price && raw_price[0] ? raw_price : "$0");
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

static void _fmt_money_sci(char *buf, size_t n, double value)
{
    char num[32] = {0};
    if (!buf || n == 0) return;
    if (value < 0) {
        _fmt_sci(num, sizeof(num), -value);
        snprintf(buf, n, "-$%s", num);
    } else {
        _fmt_sci(num, sizeof(num), value);
        snprintf(buf, n, "$%s", num);
    }
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

    _fmt_money_sci(buf, n, price);
}

void ave_fmt_change(char *buf, size_t n, double pct)
{
    const char *sign = (pct >= 0) ? "▲ +" : "▼ ";
    double abs_pct = pct < 0 ? -pct : pct;
    char num[32] = {0};
    _fmt_sci(num, sizeof(num), abs_pct);
    snprintf(buf, n, "%s%s%%", sign, num);
}

void ave_fmt_volume(char *buf, size_t n, double value)
{
    _fmt_money_sci(buf, n, value);
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
