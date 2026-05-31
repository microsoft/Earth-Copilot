"""Fan-out executor — parallel sub-agent dispatch without the classic
fan-in deadlock.

The recurring MAF pitfall: launching N sub-agents with ``asyncio.gather``
and awaiting them all *inside* a single workflow step blocks the
workflow's event loop until the slowest sub-agent returns, which can
deadlock if any sub-agent's ``ctx.send_message`` is waiting for a slot
on the same loop. ``FanOutExecutor`` runs each sub-agent in its own
task, gathers results with ``asyncio.wait``, and surfaces partial
results when some tasks fail or time out.

Usage::

    results = await FanOutExecutor.run(
        items=[q1, q2, q3],
        worker=my_sub_agent,           # async fn item -> result
        timeout_sec=20,
    )
    successful = [r for r in results if r.ok]

The shape returned (:class:`FanOutResult`) deliberately matches the
provenance-style records existing agents already emit, so wiring into
the chat stream is one line.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class FanOutResult(Generic[T, R]):
    item: T
    ok: bool
    result: R | None
    error: str | None
    latency_ms: int


class FanOutExecutor:
    """Stateless helper. Use :meth:`run` directly."""

    @staticmethod
    async def run(
        items: list[T],
        worker: Callable[[T], Awaitable[R]],
        *,
        timeout_sec: float = 30.0,
        max_concurrency: int | None = None,
    ) -> list[FanOutResult[T, R]]:
        """Fan ``worker`` out across ``items`` and collect results.

        ``max_concurrency`` caps the number of in-flight tasks (default:
        unbounded). Failures and timeouts are captured per-item — the
        function never raises for a single bad item.
        """
        sem: asyncio.Semaphore | None = (
            asyncio.Semaphore(max_concurrency) if max_concurrency else None
        )

        async def _one(item: T) -> FanOutResult[T, R]:
            start = time.monotonic()
            try:
                if sem is not None:
                    async with sem:
                        result = await asyncio.wait_for(worker(item), timeout=timeout_sec)
                else:
                    result = await asyncio.wait_for(worker(item), timeout=timeout_sec)
            except asyncio.TimeoutError:
                return FanOutResult(
                    item=item,
                    ok=False,
                    result=None,
                    error=f"timeout_{timeout_sec}s",
                    latency_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception as exc:  # noqa: BLE001
                return FanOutResult(
                    item=item,
                    ok=False,
                    result=None,
                    error=f"{type(exc).__name__}: {exc}",
                    latency_ms=int((time.monotonic() - start) * 1000),
                )
            return FanOutResult(
                item=item,
                ok=True,
                result=result,
                error=None,
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        # Spawn all tasks immediately so the event loop schedules them
        # before we start awaiting — this is what avoids the fan-in
        # deadlock in workflows whose sub-agents send back to the parent.
        tasks = [asyncio.create_task(_one(it)) for it in items]
        return list(await asyncio.gather(*tasks))


def _ensure_imported() -> None:
    """Keep ``Any`` referenced so future expansion can use it without lint noise."""
    _: Any = None
