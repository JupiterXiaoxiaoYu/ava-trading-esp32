#include "ave_json_utils.h"

#include <stdint.h>

static int _hex_val(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
    if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
    return -1;
}

static int _parse_u16(const char *p, uint16_t *out)
{
    int v0, v1, v2, v3;
    if (!p || !out) return 0;
    v0 = _hex_val(p[0]);
    v1 = _hex_val(p[1]);
    v2 = _hex_val(p[2]);
    v3 = _hex_val(p[3]);
    if (v0 < 0 || v1 < 0 || v2 < 0 || v3 < 0) return 0;
    *out = (uint16_t)((v0 << 12) | (v1 << 8) | (v2 << 4) | v3);
    return 1;
}

static void _append_byte(char *out, size_t out_n, size_t *idx, unsigned char ch)
{
    if (!out || !idx || out_n == 0) return;
    if (*idx + 1 < out_n) out[(*idx)++] = (char)ch;
}

static void _append_utf8(char *out, size_t out_n, size_t *idx, uint32_t cp)
{
    if (cp <= 0x7F) {
        _append_byte(out, out_n, idx, (unsigned char)cp);
    } else if (cp <= 0x7FF) {
        _append_byte(out, out_n, idx, (unsigned char)(0xC0 | (cp >> 6)));
        _append_byte(out, out_n, idx, (unsigned char)(0x80 | (cp & 0x3F)));
    } else if (cp <= 0xFFFF) {
        _append_byte(out, out_n, idx, (unsigned char)(0xE0 | (cp >> 12)));
        _append_byte(out, out_n, idx, (unsigned char)(0x80 | ((cp >> 6) & 0x3F)));
        _append_byte(out, out_n, idx, (unsigned char)(0x80 | (cp & 0x3F)));
    } else {
        _append_byte(out, out_n, idx, (unsigned char)(0xF0 | (cp >> 18)));
        _append_byte(out, out_n, idx, (unsigned char)(0x80 | ((cp >> 12) & 0x3F)));
        _append_byte(out, out_n, idx, (unsigned char)(0x80 | ((cp >> 6) & 0x3F)));
        _append_byte(out, out_n, idx, (unsigned char)(0x80 | (cp & 0x3F)));
    }
}

int ave_json_decode_quoted(const char *p, char *out, size_t out_n, const char **after)
{
    size_t idx = 0;

    if (!p || !out || out_n == 0 || *p != '"') return 0;

    p++;
    while (*p) {
        if (*p == '"') {
            out[idx] = '\0';
            if (after) *after = p + 1;
            return 1;
        }

        if (*p != '\\') {
            _append_byte(out, out_n, &idx, (unsigned char)*p++);
            continue;
        }

        p++;
        if (!*p) break;

        switch (*p) {
            case '"':  _append_byte(out, out_n, &idx, '"');  p++; break;
            case '\\': _append_byte(out, out_n, &idx, '\\'); p++; break;
            case '/':  _append_byte(out, out_n, &idx, '/');  p++; break;
            case 'b':  _append_byte(out, out_n, &idx, '\b'); p++; break;
            case 'f':  _append_byte(out, out_n, &idx, '\f'); p++; break;
            case 'n':  _append_byte(out, out_n, &idx, '\n'); p++; break;
            case 'r':  _append_byte(out, out_n, &idx, '\r'); p++; break;
            case 't':  _append_byte(out, out_n, &idx, '\t'); p++; break;
            case 'u': {
                uint16_t hi = 0;
                uint32_t cp = 0xFFFD;
                if (_parse_u16(p + 1, &hi)) {
                    p += 5;
                    cp = hi;
                    if (hi >= 0xD800 && hi <= 0xDBFF && p[0] == '\\' && p[1] == 'u') {
                        uint16_t lo = 0;
                        if (_parse_u16(p + 2, &lo) && lo >= 0xDC00 && lo <= 0xDFFF) {
                            cp = 0x10000 + ((((uint32_t)hi - 0xD800) << 10) | ((uint32_t)lo - 0xDC00));
                            p += 6;
                        }
                    }
                } else {
                    p++;
                }
                _append_utf8(out, out_n, &idx, cp);
                break;
            }
            default:
                _append_byte(out, out_n, &idx, (unsigned char)*p++);
                break;
        }
    }

    out[idx] = '\0';
    if (after) *after = p;
    return 0;
}
