/**
 * @file ave_price_fmt.c
 */
#include "ave_price_fmt.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

void ave_fmt_price(char *buf, size_t n, double price)
{
    if (price == 0.0) {
        snprintf(buf, n, "$0");
        return;
    }
    if (price < 0) price = -price;

    if (price >= 1000.0) {
        snprintf(buf, n, "$%.0f", price);
    } else if (price >= 1.0) {
        snprintf(buf, n, "$%.4f", price);
    } else if (price >= 0.01) {
        snprintf(buf, n, "$%.6f", price);
    } else {
        /* Find first significant digit position */
        int mag = (int)floor(log10(price));  /* negative */
        int decimals = -mag + 3;             /* e.g. 0.0000234 → mag=-5 → decimals=8 */
        if (decimals > 12) decimals = 12;
        snprintf(buf, n, "$%.*f", decimals, price);
    }
}

void ave_fmt_change(char *buf, size_t n, double pct)
{
    const char *sign = (pct >= 0) ? "▲ +" : "▼ ";
    double abs_pct = pct < 0 ? -pct : pct;
    snprintf(buf, n, "%s%.2f%%", sign, abs_pct);
}

void ave_fmt_volume(char *buf, size_t n, double value)
{
    if (value < 0) value = -value;
    if (value >= 1e9) {
        snprintf(buf, n, "$%.1fB", value / 1e9);
    } else if (value >= 1e6) {
        snprintf(buf, n, "$%.1fM", value / 1e6);
    } else if (value >= 1e3) {
        snprintf(buf, n, "$%.1fK", value / 1e3);
    } else {
        snprintf(buf, n, "$%.0f", value);
    }
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
