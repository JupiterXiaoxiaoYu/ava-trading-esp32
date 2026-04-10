#include <stdio.h>
#include <string.h>

#include "ave_font_provider.h"

int main(void)
{
    const char *path = ave_font_debug_sim_misans_path();
    if (path == NULL || path[0] == '\0') {
        fprintf(stderr, "FAIL: MiSans path was not resolved.\n");
        return 1;
    }
    if (strstr(path, "MiSans") == NULL) {
        fprintf(stderr, "FAIL: resolved path is not a MiSans font: %s\n", path);
        return 1;
    }
    printf("PASS: MiSans path resolved: %s\n", path);
    return 0;
}
