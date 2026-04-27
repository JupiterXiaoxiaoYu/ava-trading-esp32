#ifndef AVE_TRANSPORT_H
#define AVE_TRANSPORT_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Send a JSON string to the server.
 * Platform-agnostic wrapper: simulator uses ws_client, hardware uses its own transport.
 */
void ave_send_json(const char *json);

#ifdef __cplusplus
}
#endif
#endif /* AVE_TRANSPORT_H */
