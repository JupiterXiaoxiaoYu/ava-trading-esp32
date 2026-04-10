#include "ave_font_provider.h"

#include <stdio.h>
#include <string.h>

#if defined(LV_SIMULATOR) && LV_USE_TINY_TTF && LV_TINY_TTF_FILE_SUPPORT
#include "src/libs/tiny_ttf/lv_tiny_ttf.h"

#include <dirent.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

#if defined(LV_SIMULATOR) && LV_USE_TINY_TTF && LV_TINY_TTF_FILE_SUPPORT
static lv_font_t *s_cjk_14 = NULL;
static lv_font_t *s_cjk_16 = NULL;
static char s_misans_path[512] = {0};
static char s_misans_lvgl_path[516] = {0};
static int s_font_probe_done = 0;

static int _is_font_file_name(const char *name)
{
    const char *ext;
    if (!name) return 0;
    ext = strrchr(name, '.');
    if (!ext) return 0;
    return strcmp(ext, ".ttf") == 0 || strcmp(ext, ".otf") == 0 || strcmp(ext, ".ttc") == 0;
}

static int _copy_if_readable(char *out, size_t out_n, const char *path)
{
    struct stat st;
    if (!path || !path[0]) return 0;
    if (stat(path, &st) != 0 || !S_ISREG(st.st_mode) || access(path, R_OK) != 0) return 0;
    snprintf(out, out_n, "%s", path);
    return 1;
}

static int _try_candidate_file(char *out, size_t out_n, const char *dir, const char *file)
{
    char path[512];
    if (!dir || !file) return 0;
    snprintf(path, sizeof(path), "%s/%s", dir, file);
    return _copy_if_readable(out, out_n, path);
}

static int _probe_misans_from_dir(char *out, size_t out_n, const char *dir)
{
    static const char *PREFERRED_FILES[] = {
        "MiSans-Regular.ttf",
        "MiSans-Normal.ttf",
        "MiSans VF.ttf",
        "MiSans-Regular.otf",
        "MiSans-Normal.otf",
    };
    DIR *dp;
    struct dirent *ent;
    size_t i;

    for (i = 0; i < sizeof(PREFERRED_FILES) / sizeof(PREFERRED_FILES[0]); i++) {
        if (_try_candidate_file(out, out_n, dir, PREFERRED_FILES[i])) return 1;
    }

    dp = opendir(dir);
    if (!dp) return 0;

    while ((ent = readdir(dp)) != NULL) {
        char path[512];
        if (ent->d_name[0] == '.') continue;
        if (strstr(ent->d_name, "MiSans") == NULL) continue;
        if (!_is_font_file_name(ent->d_name)) continue;
        snprintf(path, sizeof(path), "%s/%s", dir, ent->d_name);
        if (_copy_if_readable(out, out_n, path)) {
            closedir(dp);
            return 1;
        }
    }

    closedir(dp);
    return 0;
}

static const char *_resolve_misans_path(void)
{
    static const char *SEARCH_DIRS[] = {
        "./assets/fonts",
        "./assets",
    };
    const char *env_path;
    size_t i;

    if (s_font_probe_done) return s_misans_path[0] ? s_misans_path : NULL;
    s_font_probe_done = 1;

    env_path = getenv("AVE_SIM_MISANS_PATH");
    if (_copy_if_readable(s_misans_path, sizeof(s_misans_path), env_path)) {
        return s_misans_path;
    }

    for (i = 0; i < sizeof(SEARCH_DIRS) / sizeof(SEARCH_DIRS[0]); i++) {
        if (_probe_misans_from_dir(s_misans_path, sizeof(s_misans_path), SEARCH_DIRS[i])) {
            return s_misans_path;
        }
    }

    fprintf(stderr, "[AVE font] MiSans not found under simulator assets.\n");
    return NULL;
}

static const char *_resolve_misans_lvgl_path(void)
{
    const char *path = _resolve_misans_path();
    if (!path) return NULL;
    if (!s_misans_lvgl_path[0]) {
        snprintf(s_misans_lvgl_path, sizeof(s_misans_lvgl_path), "A:%s", path);
    }
    return s_misans_lvgl_path;
}

static lv_font_t *_load_misans_font(int32_t px)
{
    const char *path = _resolve_misans_lvgl_path();
    if (!path) return NULL;
    return lv_tiny_ttf_create_file(path, px);
}
#endif

const lv_font_t *ave_font_cjk_14(void)
{
#if defined(LV_SIMULATOR) && LV_USE_TINY_TTF && LV_TINY_TTF_FILE_SUPPORT
    if (!s_cjk_14) s_cjk_14 = _load_misans_font(14);
    if (s_cjk_14) return s_cjk_14;
#endif
    return &lv_font_montserrat_14;
}

const lv_font_t *ave_font_cjk_16(void)
{
#if defined(LV_SIMULATOR) && LV_USE_TINY_TTF && LV_TINY_TTF_FILE_SUPPORT
    if (!s_cjk_16) s_cjk_16 = _load_misans_font(16);
    if (s_cjk_16) return s_cjk_16;
#endif
    return &lv_font_source_han_sans_sc_16_cjk;
}

const char *ave_font_debug_sim_misans_path(void)
{
#if defined(LV_SIMULATOR) && LV_USE_TINY_TTF && LV_TINY_TTF_FILE_SUPPORT
    return _resolve_misans_path();
#else
    return NULL;
#endif
}
