#include "ave_transport.h"
#include <stdio.h>

#ifdef LV_SIMULATOR
#include "ws_client.h"

void ave_send_json(const char *json)
{
    if (!json) return;
    ws_client_send_json(json);
}

#else
/* Hardware transport — implement for the target platform */
void ave_send_json(const char *json)
{
    /* TODO: wire to hardware WebSocket / UART / BLE transport */
    (void)json;
}
#endif
