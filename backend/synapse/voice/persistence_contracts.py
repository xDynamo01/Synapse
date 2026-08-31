from __future__ import annotations

from typing import Protocol

from synapse.voice.persistence_models import (
    VoicePersistenceHealth,
    VoiceRecord,
    VoiceRecordDraft,
    VoiceReplay,
)


class VoiceJournalPort(Protocol):
    def append(
        self, draft: VoiceRecordDraft, *, expected_revision: int | None = None
    ) -> VoiceRecord: ...

    def read_exact(self, record_id: str, fingerprint: str) -> VoiceRecord: ...

    def read_causal_range(
        self, stream_id: str, start_revision: int, end_revision: int
    ) -> tuple[VoiceRecord, ...]: ...

    def replay(self, stream_id: str) -> VoiceReplay: ...

    def stream_ids(self, prefix: str) -> tuple[str, ...]: ...

    def health(self) -> VoicePersistenceHealth: ...
