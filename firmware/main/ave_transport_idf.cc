#include "application.h"
#include "ave_transport.h"

extern "C" void ave_send_json(const char *json)
{
    if (json == nullptr) {
        return;
    }
    Application::GetInstance().SendRawJsonMessage(json);
}
