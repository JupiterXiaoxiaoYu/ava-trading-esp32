from __future__ import annotations

import asyncio

import pytest

from ava_devicekit.runtime.tasks import BackgroundTaskManager, TaskEvent


def test_background_task_manager_runs_named_periodic_tasks_until_stopped():
    async def scenario():
        ticks: list[str] = []
        events: list[TaskEvent] = []
        stopped = asyncio.Event()

        async def record_event(event: TaskEvent) -> None:
            events.append(event)
            if event.type == "stopped" and event.name == "prices":
                stopped.set()

        async def poll_prices() -> None:
            ticks.append("prices")

        manager = BackgroundTaskManager(event_callback=record_event)
        manager.add_periodic("prices", 0.01, poll_prices)
        await manager.start()
        await asyncio.sleep(0.035)
        await manager.stop()
        await asyncio.wait_for(stopped.wait(), timeout=0.1)

        assert ticks
        assert "prices" in manager.names
        assert manager.running_names == ()
        assert [event.type for event in events if event.name == "prices"].count("started") == 1
        assert any(event.type == "tick_succeeded" for event in events)
        assert any(event.type == "cancelled" for event in events)

    asyncio.run(scenario())


def test_background_task_manager_backs_off_after_exceptions_and_recovers():
    async def scenario():
        calls = 0
        events: list[TaskEvent] = []
        recovered = asyncio.Event()

        def record_event(event: TaskEvent) -> None:
            events.append(event)
            if event.type == "tick_succeeded":
                recovered.set()

        async def flaky() -> None:
            nonlocal calls
            calls += 1
            if calls <= 2:
                raise RuntimeError(f"boom {calls}")

        manager = BackgroundTaskManager(event_callback=record_event)
        manager.add_periodic(
            "flaky",
            0.05,
            flaky,
            backoff_base=0.005,
            backoff_factor=2,
            max_backoff=0.05,
        )
        await manager.start()
        await asyncio.wait_for(recovered.wait(), timeout=0.2)
        await manager.stop()

        failures = [event for event in events if event.type == "tick_failed"]
        assert [event.next_delay for event in failures[:2]] == [0.005, 0.01]
        assert failures[0].failure_count == 1
        assert isinstance(failures[0].exception, RuntimeError)
        assert calls >= 3
        assert any(event.type == "tick_succeeded" and event.failure_count == 0 for event in events)

    asyncio.run(scenario())


def test_background_task_manager_starts_and_stops_individual_tasks():
    async def scenario():
        calls: list[str] = []

        manager = BackgroundTaskManager()
        manager.add_periodic("a", 0.01, lambda: calls.append("a"))
        manager.add_periodic("b", 0.01, lambda: calls.append("b"))

        await manager.start_task("a")
        await asyncio.sleep(0.025)
        assert calls
        assert set(calls) == {"a"}

        await manager.stop_task("a")
        calls.clear()
        await manager.start_task("b")
        await asyncio.sleep(0.025)
        await manager.stop()

        assert calls
        assert set(calls) == {"b"}

    asyncio.run(scenario())


def test_background_task_manager_can_restart_registered_tasks():
    async def scenario():
        calls = 0

        async def tick() -> None:
            nonlocal calls
            calls += 1

        manager = BackgroundTaskManager()
        manager.add_periodic("restartable", 0.01, tick)

        await manager.start()
        await asyncio.sleep(0.015)
        await manager.stop()
        first_run_calls = calls

        await manager.start()
        await asyncio.sleep(0.015)
        await manager.stop()

        assert first_run_calls > 0
        assert calls > first_run_calls
        assert manager.running_names == ()

    asyncio.run(scenario())


def test_background_task_manager_validates_duplicate_and_unknown_tasks():
    manager = BackgroundTaskManager()
    manager.add_periodic("refresh", 1, lambda: None)

    with pytest.raises(ValueError):
        manager.add_periodic("refresh", 1, lambda: None)

    async def scenario():
        with pytest.raises(KeyError):
            await manager.start_task("missing")
        await manager.stop()

    asyncio.run(scenario())
