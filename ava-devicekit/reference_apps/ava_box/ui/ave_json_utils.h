#ifndef AVE_JSON_UTILS_H
#define AVE_JSON_UTILS_H

#include <stddef.h>

int ave_json_decode_quoted(const char *p, char *out, size_t out_n, const char **after);

#endif /* AVE_JSON_UTILS_H */
