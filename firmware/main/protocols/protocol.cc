#include "protocol.h"

#include "ave_screen_manager.h"

#include <esp_log.h>

#define TAG "Protocol"

namespace {

bool AppendSelectionJson(std::string& message) {
    char selection[384];
    if (!ave_sm_get_selection_context_json(selection, sizeof(selection))) {
        return false;
    }
    message += ",\"selection\":";
    message += selection;
    return true;
}

std::string BuildListenMessage(const std::string& session_id,
                              const char* state,
                              const char* text,
                              const char* mode) {
    std::string message = "{\"session_id\":\"" + session_id + "\"";
    message += ",\"type\":\"listen\",\"state\":\"";
    message += state;
    message += "\"";

    if (text != nullptr) {
        char escaped_text[256];
        if (!ave_sm_json_escape_string(text, escaped_text, sizeof(escaped_text))) {
            escaped_text[0] = '\0';
        }
        message += ",\"text\":\"";
        message += escaped_text;
        message += "\"";
    }

    if (mode != nullptr) {
        message += ",\"mode\":\"";
        message += mode;
        message += "\"";
    }

    AppendSelectionJson(message);
    message += "}";
    return message;
}

}  // namespace

void Protocol::OnIncomingJson(std::function<void(const cJSON* root)> callback) {
    on_incoming_json_ = callback;
}

void Protocol::OnIncomingAudio(std::function<void(std::unique_ptr<AudioStreamPacket> packet)> callback) {
    on_incoming_audio_ = callback;
}

void Protocol::OnAudioChannelOpened(std::function<void()> callback) {
    on_audio_channel_opened_ = callback;
}

void Protocol::OnAudioChannelClosed(std::function<void()> callback) {
    on_audio_channel_closed_ = callback;
}

void Protocol::OnNetworkError(std::function<void(const std::string& message)> callback) {
    on_network_error_ = callback;
}

void Protocol::OnConnected(std::function<void()> callback) {
    on_connected_ = callback;
}

void Protocol::OnDisconnected(std::function<void()> callback) {
    on_disconnected_ = callback;
}

void Protocol::SetError(const std::string& message) {
    error_occurred_ = true;
    if (on_network_error_ != nullptr) {
        on_network_error_(message);
    }
}

void Protocol::SendAbortSpeaking(AbortReason reason) {
    std::string message = "{\"session_id\":\"" + session_id_ + "\",\"type\":\"abort\"";
    if (reason == kAbortReasonWakeWordDetected) {
        message += ",\"reason\":\"wake_word_detected\"";
    }
    message += "}";
    SendText(message);
}

void Protocol::SendWakeWordDetected(const std::string& wake_word) {
    SendText(BuildListenMessage(session_id_, "detect", wake_word.c_str(), nullptr));
}

void Protocol::SendStartListening(ListeningMode mode) {
    const char* mode_text = "manual";
    if (mode == kListeningModeRealtime) {
        mode_text = "realtime";
    } else if (mode == kListeningModeAutoStop) {
        mode_text = "auto";
    }
    SendText(BuildListenMessage(session_id_, "start", nullptr, mode_text));
}

void Protocol::SendStopListening() {
    std::string message = "{\"session_id\":\"" + session_id_ + "\",\"type\":\"listen\",\"state\":\"stop\"}";
    SendText(message);
}

void Protocol::SendMcpMessage(const std::string& payload) {
    std::string message = "{\"session_id\":\"" + session_id_ + "\",\"type\":\"mcp\",\"payload\":" + payload + "}";
    SendText(message);
}

bool Protocol::SendRawJson(const std::string& message) {
    return SendText(message);
}

bool Protocol::IsTimeout() const {
    const int kTimeoutSeconds = 120;
    auto now = std::chrono::steady_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::seconds>(now - last_incoming_time_);
    bool timeout = duration.count() > kTimeoutSeconds;
    if (timeout) {
        ESP_LOGE(TAG, "Channel timeout %ld seconds", (long)duration.count());
    }
    return timeout;
}
