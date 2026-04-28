#include <stdio.h>
#include <string.h>

#include "ave_price_fmt.h"

static int expect_price(const char *raw, const char *expected)
{
    char out[32] = {0};
    ave_fmt_price_text(out, sizeof(out), raw);
    if (strcmp(out, expected) != 0) {
        fprintf(stderr, "FAIL: raw='%s' expected='%s' actual='%s'\n", raw, expected, out);
        return 0;
    }
    return 1;
}

static int expect_volume(double value, const char *expected)
{
    char out[32] = {0};
    ave_fmt_volume(out, sizeof(out), value);
    if (strcmp(out, expected) != 0) {
        fprintf(stderr, "FAIL: volume='%f' expected='%s' actual='%s'\n", value, expected, out);
        return 0;
    }
    return 1;
}

int main(void)
{
    int ok = 1;
    ok &= expect_price("$0.123456", "$0.1235");
    ok &= expect_price("$0.00007956", "$7.96e-5");
    ok &= expect_price("$0.0000002702", "$2.70e-7");
    ok &= expect_price("$12.34", "$12.34");
    ok &= expect_price("-$0.00007956", "-$7.96e-5");
    ok &= expect_volume(1490000.0, "$1.5M");
    ok &= expect_volume(404000.0, "$404K");
    return ok ? 0 : 1;
}
