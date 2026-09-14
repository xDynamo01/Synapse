"""Bounded bridge between synchronous governed turns and progressive transport."""

from collections.abc import Callable, Iterator
from contextvars import copy_context
from queue import Empty, Full, Queue
from threading import Event, Thread

from synapse.models.streaming import text_stream


def stream_response(work: Callable[[], str], *, fallback_text: bool = True) -> Iterator[tuple[str, str]]:
    queue: Queue[tuple[str, str]] = Queue(maxsize=64)
    closed = Event()

    def publish(kind: str, value: str) -> None:
        while not closed.is_set():
            try:
                queue.put((kind, value), timeout=0.1)
                return
            except Full:
                continue
        raise InterruptedError("Conversation stream closed")

    def run() -> None:
        try:
            with text_stream(lambda text: publish("chunk_received", text)):
                result = work()
            publish("completed", result)
        except Exception as exc:
            if not closed.is_set():
                publish("failed", str(exc))

    context = copy_context()
    worker = Thread(target=lambda: context.run(run), daemon=True, name="conversation-turn")
    worker.start()
    received = False
    try:
        while True:
            try:
                kind, value = queue.get(timeout=0.5)
            except Empty:
                continue
            if kind == "completed":
                if not received and fallback_text:
                    yield "chunk_received", value
                yield "generation_completed", value
                return
            if kind == "failed":
                raise RuntimeError(value)
            received = True
            yield kind, value
    finally:
        closed.set()
