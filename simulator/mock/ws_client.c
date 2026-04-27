/**
 * @file ws_client.c
 * @brief Minimal WebSocket client for Ava Box simulator.
 *
 * Design:
 *  - Background recv thread: connects, does HTTP upgrade, receives frames.
 *  - Incoming display messages are pushed onto a lock-free ring queue.
 *  - ws_client_poll() is called by the LVGL main thread to drain the queue
 *    and call ave_sm_handle_json() — keeping all LVGL calls on one thread.
 *  - Automatic reconnect on disconnect.
 */

#include "ws_client.h"
#include "ave_screen_manager.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <pthread.h>
#include <unistd.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <netinet/in.h>

/* ── Server coordinates ──────────────────────────────────────────────────── */
#define WS_HOST "127.0.0.1"
#define WS_PORT 8787
#define WS_PATH "/ava/v1/?device-id=ave-sim&client-id=sim-001"

/* Simulator hello for the DeviceKit legacy-compatible gateway. */
#define HELLO_MSG \
    "{\"type\":\"hello\",\"version\":3,\"transport\":\"websocket\"," \
    "\"audio_params\":{\"format\":\"pcm16\",\"sample_rate\":16000," \
    "\"channels\":1,\"frame_duration\":60}}"

/* ── Thread-safe display-message queue ───────────────────────────────────── */
/* Real-time WSS can burst many events (one per token on price update).
 * Keep the last 8 pending display frames; each FEED message is ~4KB for 12 tokens. */
#define Q_SLOTS   8
#define Q_MSG_MAX 16384

static char            s_q[Q_SLOTS][Q_MSG_MAX];
static volatile int    s_qhead = 0, s_qtail = 0;
static pthread_mutex_t s_qmu   = PTHREAD_MUTEX_INITIALIZER;

static void q_push(const char *msg, size_t len)
{
    pthread_mutex_lock(&s_qmu);
    int next = (s_qtail + 1) % Q_SLOTS;
    if (next != s_qhead) {  /* drop if full (shouldn't happen) */
        size_t n = len < Q_MSG_MAX - 1 ? len : Q_MSG_MAX - 1;
        memcpy(s_q[s_qtail], msg, n);
        s_q[s_qtail][n] = '\0';
        s_qtail = next;
    }
    pthread_mutex_unlock(&s_qmu);
}

int ws_client_poll(void)
{
    pthread_mutex_lock(&s_qmu);
    if (s_qhead == s_qtail) { pthread_mutex_unlock(&s_qmu); return 0; }
    char tmp[Q_MSG_MAX];
    strncpy(tmp, s_q[s_qhead], Q_MSG_MAX - 1);
    tmp[Q_MSG_MAX - 1] = '\0';
    s_qhead = (s_qhead + 1) % Q_SLOTS;
    pthread_mutex_unlock(&s_qmu);
    ave_sm_handle_json(tmp);   /* called on LVGL main thread */
    return 1;
}

/* ── WebSocket frame I/O ─────────────────────────────────────────────────── */

static int recv_exact(int fd, uint8_t *buf, size_t n)
{
    size_t got = 0;
    while (got < n) {
        ssize_t r = recv(fd, buf + got, n - got, 0);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return -1;
        got += (size_t)r;
    }
    return 0;
}

/* Returns malloc'd payload (caller frees), sets *opcode and *out_len. */
static char *ws_recv_frame(int fd, size_t *out_len, uint8_t *opcode)
{
    uint8_t h[2];
    if (recv_exact(fd, h, 2) < 0) return NULL;

    *opcode       = h[0] & 0x0F;
    int     masked = (h[1] >> 7) & 1;
    uint64_t plen  = h[1] & 0x7F;

    if (plen == 126) {
        uint8_t e[2];
        if (recv_exact(fd, e, 2) < 0) return NULL;
        plen = ((uint64_t)e[0] << 8) | e[1];
    } else if (plen == 127) {
        uint8_t e[8];
        if (recv_exact(fd, e, 8) < 0) return NULL;
        plen = 0;
        for (int i = 0; i < 8; i++) plen = (plen << 8) | e[i];
    }

    uint8_t mask[4] = {0};
    if (masked && recv_exact(fd, mask, 4) < 0) return NULL;

    if (plen > 1024 * 1024) return NULL;  /* sanity cap */

    char *payload = (char *)malloc(plen + 1);
    if (!payload) return NULL;
    if (plen && recv_exact(fd, (uint8_t *)payload, plen) < 0) {
        free(payload); return NULL;
    }
    if (masked)
        for (uint64_t i = 0; i < plen; i++) payload[i] ^= mask[i & 3];
    payload[plen] = '\0';
    *out_len = (size_t)plen;
    return payload;
}

/* Send a masked text frame (client → server must be masked per RFC 6455). */
static int ws_send_frame(int fd, const char *data, size_t len)
{
    uint8_t hdr[4];
    int hlen;
    hdr[0] = 0x81;  /* FIN + text opcode */
    if (len < 126) {
        hdr[1] = 0x80 | (uint8_t)len;
        hlen = 2;
    } else if (len < 65536) {
        hdr[1] = 0x80 | 126;
        hdr[2] = (uint8_t)(len >> 8);
        hdr[3] = (uint8_t)(len & 0xFF);
        hlen = 4;
    } else {
        return -1;
    }

    static const uint8_t mask[4] = {0x37, 0xfa, 0x21, 0x3d};
    uint8_t *buf = (uint8_t *)malloc(hlen + 4 + len);
    if (!buf) return -1;
    memcpy(buf, hdr, hlen);
    memcpy(buf + hlen, mask, 4);
    for (size_t i = 0; i < len; i++)
        buf[hlen + 4 + i] = ((const uint8_t *)data)[i] ^ mask[i & 3];

    int r = (int)send(fd, buf, hlen + 4 + len, MSG_NOSIGNAL);
    free(buf);
    return r < 0 ? -1 : 0;
}

/* ── HTTP upgrade handshake ──────────────────────────────────────────────── */

static int ws_connect(void)
{
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port   = htons(WS_PORT);
    inet_pton(AF_INET, WS_HOST, &addr.sin_addr);

    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(fd); return -1;
    }

    char req[512];
    snprintf(req, sizeof(req),
        "GET " WS_PATH " HTTP/1.1\r\n"
        "Host: " WS_HOST ":%d\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n", WS_PORT);
    if (send(fd, req, strlen(req), MSG_NOSIGNAL) < 0) { close(fd); return -1; }

    /* Read until end of HTTP headers */
    char resp[2048];
    int pos = 0;
    while (pos < (int)sizeof(resp) - 1) {
        if (recv(fd, resp + pos, 1, 0) <= 0) { close(fd); return -1; }
        pos++;
        if (pos >= 4 && memcmp(resp + pos - 4, "\r\n\r\n", 4) == 0) break;
    }
    resp[pos] = '\0';

    if (!strstr(resp, "101")) { close(fd); return -1; }
    return fd;
}

/* ── State ───────────────────────────────────────────────────────────────── */
static volatile int    s_running   = 0;
static volatile int    s_connected = 0;
static pthread_t       s_recv_tid;
static int             s_fd        = -1;
static pthread_mutex_t s_mu        = PTHREAD_MUTEX_INITIALIZER;

/* ── Receive thread ──────────────────────────────────────────────────────── */
static void *_recv_thread(void *arg)
{
    (void)arg;

    while (s_running) {
        int fd = ws_connect();
        if (fd < 0) {
            if (s_running)
                printf("[AVE ws] Server offline — start DeviceKit gateway on 127.0.0.1:8787\n");
            for (int i = 0; i < 3 && s_running; i++) sleep(1);
            continue;
        }

        pthread_mutex_lock(&s_mu);
        s_fd = fd; s_connected = 1;
        pthread_mutex_unlock(&s_mu);

        printf("[AVE ws] Connected to server.\n");
        ws_send_frame(fd, HELLO_MSG, strlen(HELLO_MSG));
        printf("[AVE ws] Type a command in this terminal and press Enter.\n");

        while (s_running) {
            uint8_t opcode;
            size_t  plen;
            char   *payload = ws_recv_frame(fd, &plen, &opcode);
            if (!payload) break;

            switch (opcode) {
                case 0x8:  /* close */
                    free(payload); goto disconnect;
                case 0x9: { /* ping → pong (RFC 6455 §5.5.3)
                             * Client→server frames MUST be masked (RFC 6455 §5.1).
                             * Previous fix echoed payload but forgot the mask bit —
                             * websockets 16.0 validates masking and closes on violation. */
                    static const uint8_t mk[4] = {0x37, 0xfa, 0x21, 0x3d};
                    size_t pl = plen;
                    uint8_t hdr[8];  /* 2 or 4 header bytes + 4 mask bytes */
                    int hlen;
                    hdr[0] = 0x8A;  /* FIN + pong opcode */
                    if (pl < 126) {
                        hdr[1] = 0x80 | (uint8_t)pl;  /* mask bit SET */
                        hlen = 2;
                    } else {
                        hdr[1] = 0x80 | 126;
                        hdr[2] = (uint8_t)(pl >> 8);
                        hdr[3] = (uint8_t)(pl & 0xFF);
                        hlen = 4;
                    }
                    memcpy(hdr + hlen, mk, 4);
                    hlen += 4;
                    /* Mask payload in-place (payload is malloc'd, safe to modify) */
                    for (uint64_t i = 0; i < pl; i++) payload[i] ^= mk[i & 3];
                    send(fd, hdr, hlen, MSG_NOSIGNAL);
                    if (pl > 0) send(fd, payload, pl, MSG_NOSIGNAL);
                    break;
                }
                case 0x1:  /* text frame */
                case 0x0:  /* continuation */
                    q_push(payload, plen);
                    break;
                /* 0x2 = binary (audio), silently discard */
            }
            free(payload);
        }

    disconnect:
        pthread_mutex_lock(&s_mu);
        s_fd = -1; s_connected = 0;
        pthread_mutex_unlock(&s_mu);
        close(fd);

        if (s_running) {
            printf("[AVE ws] Disconnected — reconnecting in 2s...\n");
            sleep(2);
        }
    }
    return NULL;
}

/* ── Public API ──────────────────────────────────────────────────────────── */

void ws_client_start(void)
{
    s_running = 1;
    pthread_create(&s_recv_tid, NULL, _recv_thread, NULL);
}

void ws_client_stop(void)
{
    s_running = 0;
    pthread_mutex_lock(&s_mu);
    if (s_fd >= 0) shutdown(s_fd, SHUT_RDWR);  /* unblock blocking recv() */
    pthread_mutex_unlock(&s_mu);
    pthread_join(s_recv_tid, NULL);
}

void ws_client_send_text(const char *text)
{
    char msg[1024];
    if (!ave_sm_build_listen_detect_json(text, msg, sizeof(msg))) {
        printf("[AVE ws] failed to build listen.detect payload\n");
        return;
    }

    pthread_mutex_lock(&s_mu);
    int fd = s_fd;
    int ok = s_connected && fd >= 0;
    pthread_mutex_unlock(&s_mu);

    if (ok) {
        ws_send_frame(fd, msg, strlen(msg));
        printf("[AVE ws] sent: \"%s\"\n", text);
    } else {
        printf("[AVE ws] not connected — start server: cd ava-devicekit && PYTHONPATH=backend python3 -m ava_devicekit.cli run-legacy-ws --config userland/runtime.example.json\n");
    }
}

void ws_client_send_json(const char *json)
{
    /* Send a pre-formed JSON string directly to the server (no listen wrapper). */
    pthread_mutex_lock(&s_mu);
    int fd = s_fd;
    int ok = s_connected && fd >= 0;
    pthread_mutex_unlock(&s_mu);

    if (ok) {
        ws_send_frame(fd, json, strlen(json));
        printf("[AVE ws] sent JSON: %.80s\n", json);
    } else {
        printf("[AVE ws] not connected — start server: cd ava-devicekit && PYTHONPATH=backend python3 -m ava_devicekit.cli run-legacy-ws --config userland/runtime.example.json\n");
    }
}

int ws_client_connected(void)
{
    return s_connected;
}
