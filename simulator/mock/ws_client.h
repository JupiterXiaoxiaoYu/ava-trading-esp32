/**
 * @file ws_client.h
 * @brief WebSocket client for Ava Box simulator.
 *
 * Mirrors the hardware ESP32 WebSocket connection to the DeviceKit gateway.
 * Receives {"type":"display",...} messages and routes them to the screen
 * manager — identical to what the firmware does over its WSS connection.
 *
 * Text injection (replaces voice input in the simulator):
 *   ws_client_send_text("帮我看热门代币")
 *   → sends {"type":"listen","state":"detect","text":"...","selection":{...}}
 *     when the current AVE screen has an explicit selection context
 *   → server ASR bypass → LLM → ave_tools → display message back
 */

#ifndef WS_CLIENT_H
#define WS_CLIENT_H

#ifdef __cplusplus
extern "C" {
#endif

/** Connect to the server and start the receive thread. Non-blocking. */
void ws_client_start(void);

/** Stop receive thread and close connection. Blocks until thread exits. */
void ws_client_stop(void);

/**
 * Send a text command to the server (bypasses ASR, goes straight to LLM).
 * Thread-safe; may be called from any thread.
 */
void ws_client_send_text(const char *text);

/**
 * Send a pre-formed JSON string directly (bypasses the listen/LLM wrapper).
 * Use for key_action and trade_action messages.
 * Thread-safe; may be called from any thread.
 */
void ws_client_send_json(const char *json);

/** 1 if currently connected, 0 otherwise. */
int ws_client_connected(void);

/**
 * Process one pending display message from the queue.
 * MUST be called from the LVGL main thread (not thread-safe with LVGL).
 * Returns 1 if a message was processed, 0 if the queue was empty.
 * Call in a tight loop until it returns 0.
 */
int ws_client_poll(void);

#ifdef __cplusplus
}
#endif

#endif /* WS_CLIENT_H */
