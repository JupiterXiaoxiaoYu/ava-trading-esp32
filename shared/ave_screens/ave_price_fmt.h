/**
 * @file ave_price_fmt.h
 * @brief Price formatting helpers for LVGL labels.
 *
 * Handles extreme-small prices (e.g. BONK = 0.0000234) correctly.
 * lv_chart requires int16 values — use ave_price_to_chart() for log normalization.
 */

#ifndef AVE_PRICE_FMT_H
#define AVE_PRICE_FMT_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>

/**
 * Format a price as "$X.XXXXX" into buf.
 * Automatically picks appropriate decimal places.
 * price == 0  → "$0"
 * price >= 1  → "$1.2345"
 * price < 0.01 → finds first significant digit, adds 3 more decimals
 */
void ave_fmt_price(char *buf, size_t n, double price);

/**
 * Compact an already formatted price string when it has too many leading zeros.
 * Example: "$0.00007956" -> "$7.96e-5"
 */
void ave_fmt_price_text(char *buf, size_t n, const char *raw_price);

/**
 * Format a percentage change: "+12.34%" or "-5.67%"
 */
void ave_fmt_change(char *buf, size_t n, double pct);

/**
 * Format a large number as "$1.2M" / "$890K" / "$123"
 */
void ave_fmt_volume(char *buf, size_t n, double value);

/**
 * Log-normalize a price for lv_chart (prevents flat-line for tiny prices).
 *
 * Given a price value and the known [price_min, price_max] range of the
 * data set, returns an int16 in range [0, 1000].
 *
 * If price_min <= 0 or price_min == price_max, falls back to linear scaling.
 */
int16_t ave_price_to_chart(double price, double price_min, double price_max);

#ifdef __cplusplus
}
#endif

#endif /* AVE_PRICE_FMT_H */
