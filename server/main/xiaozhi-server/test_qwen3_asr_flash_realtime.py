from core.providers.asr.qwen3_asr_flash_realtime import ASRProvider


def test_manual_session_update_disables_turn_detection():
    provider = ASRProvider(
        {
            "api_key": "test-key",
            "language": "zh",
            "sample_rate": 16000,
        },
        delete_audio_file=True,
    )

    event = provider._build_session_update_event(manual_mode=True)

    assert event["type"] == "session.update"
    assert event["session"]["turn_detection"] is None
    assert event["session"]["input_audio_transcription"]["language"] == "zh"


def test_server_event_parser_surfaces_ready_and_final_transcript():
    provider = ASRProvider(
        {
            "api_key": "test-key",
        },
        delete_audio_file=True,
    )

    ready = provider._process_server_event({"type": "session.updated"})
    assert ready["server_ready"] is True
    assert ready["final_transcript"] is None

    completed = provider._process_server_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "进入代币详情页",
            "language": "zh",
            "emotion": "neutral",
        }
    )
    assert completed["server_ready"] is False
    assert completed["final_transcript"] == "进入代币详情页"
