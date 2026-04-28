"""Asyncio-backed background task scheduling for AVA DeviceKit runtimes."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

TaskEventType = Literal[
    "registered",
    "started",
    "tick_succeeded",
    "tick_failed",
    "stopped",
    "cancelled",
]
TaskCallback = Callable[[], Awaitable[Any] | Any]
TaskEventCallback = Callable[["TaskEvent"], Awaitable[Any] | Any]


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """Lifecycle and execution event emitted by a background task."""

    name: str
    type: TaskEventType
    timestamp: float
    run_count: int = 0
    failure_count: int = 0
    next_delay: float | None = None
    exception: BaseException | None = None


@dataclass(frozen=True, slots=True)
class PeriodicTask:
    """Configuration for a named periodic background task."""

    name: str
    interval: float
    callback: TaskCallback
    initial_delay: float = 0.0
    backoff_base: float | None = None
    backoff_factor: float = 2.0
    max_backoff: float | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("task name must not be empty")
        if self.interval <= 0:
            raise ValueError("task interval must be greater than zero")
        if self.initial_delay < 0:
            raise ValueError("initial delay must not be negative")
        if self.backoff_base is not None and self.backoff_base <= 0:
            raise ValueError("backoff base must be greater than zero")
        if self.backoff_factor < 1:
            raise ValueError("backoff factor must be at least one")
        if self.max_backoff is not None and self.max_backoff <= 0:
            raise ValueError("max backoff must be greater than zero")

    def next_backoff(self, failure_count: int) -> float:
        base = self.backoff_base if self.backoff_base is not None else self.interval
        delay = base * (self.backoff_factor ** max(failure_count - 1, 0))
        if self.max_backoff is not None:
            delay = min(delay, self.max_backoff)
        return delay


class BackgroundTaskManager:
    """Run named periodic coroutines on the current asyncio event loop.

    Tasks are cooperative asyncio tasks. A failing callback does not stop its
    task; the next run is delayed using exponential backoff and the failure is
    reported through the optional event callback.
    """

    def __init__(self, event_callback: TaskEventCallback | None = None) -> None:
        self._event_callback = event_callback
        self._registry: dict[str, PeriodicTask] = {}
        self._running: dict[str, asyncio.Task[None]] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._registry)

    @property
    def running_names(self) -> tuple[str, ...]:
        return tuple(self._running)

    def add_periodic(
        self,
        name: str,
        interval: float,
        callback: TaskCallback,
        *,
        initial_delay: float = 0.0,
        backoff_base: float | None = None,
        backoff_factor: float = 2.0,
        max_backoff: float | None = None,
    ) -> PeriodicTask:
        """Register a named periodic callback.

        If the manager is already running, call ``start_task`` to launch the new
        registration. Keeping registration explicit avoids hidden await points.
        """

        if name in self._registry:
            raise ValueError(f"background task already registered: {name}")
        task = PeriodicTask(
            name=name,
            interval=interval,
            callback=callback,
            initial_delay=initial_delay,
            backoff_base=backoff_base,
            backoff_factor=backoff_factor,
            max_backoff=max_backoff,
        )
        self._registry[name] = task
        self._schedule_event(TaskEvent(name=name, type="registered", timestamp=time.time()))
        return task

    async def start(self) -> None:
        """Start all registered tasks that are not already running."""

        for name in self._registry:
            await self.start_task(name)

    async def start_task(self, name: str) -> None:
        """Start one registered task by name."""

        if name not in self._registry:
            raise KeyError(name)
        existing = self._running.get(name)
        if existing is not None and not existing.done():
            return
        worker = asyncio.create_task(self._run_periodic(self._registry[name]), name=f"ava-devicekit:{name}")
        self._running[name] = worker

    async def stop(self) -> None:
        """Cancel all running tasks. Registered tasks can be started again later."""

        workers = list(self._running.values())
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self._running.clear()

    async def stop_task(self, name: str) -> None:
        """Cancel one running task by name without unregistering it."""

        worker = self._running.pop(name, None)
        if worker is None:
            return
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)

    async def _run_periodic(self, task: PeriodicTask) -> None:
        run_count = 0
        failure_count = 0
        try:
            await self._emit(TaskEvent(name=task.name, type="started", timestamp=time.time()))
            if task.initial_delay:
                await asyncio.sleep(task.initial_delay)
            while True:
                try:
                    result = task.callback()
                    if inspect.isawaitable(result):
                        await result
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - scheduler must contain task failures.
                    failure_count += 1
                    delay = task.next_backoff(failure_count)
                    await self._emit(
                        TaskEvent(
                            name=task.name,
                            type="tick_failed",
                            timestamp=time.time(),
                            run_count=run_count,
                            failure_count=failure_count,
                            next_delay=delay,
                            exception=exc,
                        )
                    )
                    await asyncio.sleep(delay)
                    continue

                run_count += 1
                failure_count = 0
                await self._emit(
                    TaskEvent(
                        name=task.name,
                        type="tick_succeeded",
                        timestamp=time.time(),
                        run_count=run_count,
                        failure_count=failure_count,
                        next_delay=task.interval,
                    )
                )
                await asyncio.sleep(task.interval)
        except asyncio.CancelledError:
            await self._emit(
                TaskEvent(
                    name=task.name,
                    type="cancelled",
                    timestamp=time.time(),
                    run_count=run_count,
                    failure_count=failure_count,
                )
            )
            raise
        finally:
            self._running.pop(task.name, None)
            await self._emit(
                TaskEvent(
                    name=task.name,
                    type="stopped",
                    timestamp=time.time(),
                    run_count=run_count,
                    failure_count=failure_count,
                )
            )

    async def _emit(self, event: TaskEvent) -> None:
        if self._event_callback is None:
            return
        try:
            result = self._event_callback(event)
            if inspect.isawaitable(result):
                await result
        except Exception:
            # Observability hooks must not disrupt runtime background work.
            return

    def _schedule_event(self, event: TaskEvent) -> None:
        if self._event_callback is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._emit(event))


__all__ = [
    "BackgroundTaskManager",
    "PeriodicTask",
    "TaskCallback",
    "TaskEvent",
    "TaskEventCallback",
    "TaskEventType",
]
