"""Request-local delivery of generated text, independent of transport and persistence."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_text_sink: ContextVar[Callable[[str], None] | None] = ContextVar("model_text_sink", default=None)


@contextmanager
def text_stream(sink: Callable[[str], None]) -> Iterator[None]:
    token = _text_sink.set(sink)
    try:
        yield
    finally:
        _text_sink.reset(token)


def streaming_requested() -> bool:
    return _text_sink.get() is not None


def emit_text(text: str) -> None:
    sink = _text_sink.get()
    if sink is not None and text:
        sink(text)
