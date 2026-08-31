"""Deterministic plain-text and static-HTML extraction without I/O or retrieval."""

from __future__ import annotations

import codecs
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from threading import Lock
from typing import Protocol

from synapse.search import (
    ArtifactContentReference,
    CharsetSource,
    ExtractedContentChecksum,
    ExtractedContentId,
    ExtractedContentReference,
    ExtractedContentV1,
    ExtractionAttemptId,
    ExtractionCapability,
    ExtractionOutcome,
    ExtractionProvenance,
    ExtractionRequestV1,
    ExtractorReference,
    RetrievalOutcome,
    RetrievedArtifactV1,
    SearchOccurrence,
    SearchValidationError,
)

TEXT_EXTRACTION_ADAPTER_VERSION = "text-extraction-adapter-v1"
_EXTRACTOR = ExtractorReference("extractor:text-extraction-v1")
_CHARSET_PARAMETER = re.compile(r"(?:^|;)\s*charset\s*=\s*[\"']?([^;\s\"']+)", re.I)
_BLOCK_TAGS = frozenset(
    {
        "address", "article", "aside", "blockquote", "body", "br", "dd", "div", "dl",
        "dt", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
        "header", "hr", "li", "main", "nav", "ol", "p", "section", "table", "tr", "ul",
    }
)
_HIDDEN_TAGS = frozenset({"script", "style", "noscript", "template", "iframe"})


class ArtifactContentReader(Protocol):
    def read(self, reference: ArtifactContentReference) -> bytes: ...


@dataclass(frozen=True, slots=True)
class TextExtractionAdapterConfig:
    maximum_characters: int = 1_000_000

    def __post_init__(self) -> None:
        if (
            isinstance(self.maximum_characters, bool)
            or not isinstance(self.maximum_characters, int)
            or not 1 <= self.maximum_characters <= 10_000_000
        ):
            raise SearchValidationError("extraction character limit is invalid")


@dataclass(frozen=True, slots=True)
class TextExtractionHealth:
    adapter_implemented: bool
    plain_text_supported: bool
    static_html_supported: bool
    pdf_supported: bool
    javascript_rendering_supported: bool
    browser_applicable: bool


class TransientExtractedContentStore:
    """Process-local extracted text with explicit release and no persistence."""

    def __init__(self) -> None:
        self._items: dict[ExtractedContentReference, str] = {}
        self._lock = Lock()

    def put(self, reference: ExtractedContentReference, text: str) -> None:
        with self._lock:
            existing = self._items.get(reference)
            if existing is not None and existing != text:
                raise SearchValidationError("transient extracted content reference already exists")
            self._items[reference] = text

    def read(self, reference: ExtractedContentReference) -> str:
        with self._lock:
            try:
                return self._items[reference]
            except KeyError as error:
                raise SearchValidationError("transient extracted content is unavailable") from error

    def release(self, reference: ExtractedContentReference) -> None:
        with self._lock:
            self._items.pop(reference, None)

    def contains(self, reference: ExtractedContentReference) -> bool:
        with self._lock:
            return reference in self._items


class _StructuralHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0
        self.pre_depth = 0
        self.declared_charset: str | None = None
        self.declared_language: str | None = None
        self._open_tags: list[str] = []
        self.tolerant_recovery = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value for name, value in attrs}
        if tag == "html" and values.get("lang"):
            self.declared_language = values["lang"]
        if tag == "meta":
            charset = values.get("charset")
            content = values.get("content") or ""
            if charset:
                self.declared_charset = charset.strip()
            elif (values.get("http-equiv") or "").lower() == "content-type":
                match = _CHARSET_PARAMETER.search(content)
                if match:
                    self.declared_charset = match.group(1)
        if tag in _HIDDEN_TAGS:
            self.hidden_depth += 1
        if tag == "pre":
            self.pre_depth += 1
        if tag in _BLOCK_TAGS and self.hidden_depth == 0:
            self.parts.append("\n- " if tag == "li" else "\n\n")
        elif tag in {"td", "th"} and self.hidden_depth == 0:
            self.parts.append("\t")
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self._open_tags.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._open_tags and self._open_tags[-1] == tag:
            self._open_tags.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN_TAGS and self.hidden_depth:
            self.hidden_depth -= 1
        if tag == "pre" and self.pre_depth:
            self.pre_depth -= 1
        if tag in _BLOCK_TAGS and self.hidden_depth == 0:
            self.parts.append("\n\n")
        if tag in self._open_tags:
            while self._open_tags:
                opened = self._open_tags.pop()
                if opened == tag:
                    break
                self.tolerant_recovery = True
        else:
            self.tolerant_recovery = True

    def handle_data(self, data: str) -> None:
        if self.hidden_depth == 0:
            self.parts.append(data if self.pre_depth else re.sub(r"\s+", " ", data))

    def close(self) -> None:
        super().close()
        if self._open_tags:
            self.tolerant_recovery = True


class TextExtractionAdapter:
    def __init__(
        self,
        artifact_reader: ArtifactContentReader,
        config: TextExtractionAdapterConfig | None = None,
        content_store: TransientExtractedContentStore | None = None,
    ) -> None:
        self._artifact_reader = artifact_reader
        self._config = config or TextExtractionAdapterConfig()
        self._content_store = content_store or TransientExtractedContentStore()

    @property
    def health(self) -> TextExtractionHealth:
        return TextExtractionHealth(True, True, True, False, False, False)

    @property
    def content_store(self) -> TransientExtractedContentStore:
        return self._content_store

    def extract(
        self,
        request: ExtractionRequestV1,
        artifact: RetrievedArtifactV1,
        attempt_id: ExtractionAttemptId,
    ) -> ExtractedContentV1:
        self._validate_correspondence(request, artifact)
        if artifact.content_reference is None:
            return self._result(request, artifact, attempt_id, ExtractionOutcome.ARTIFACT_UNAVAILABLE)
        if not self._supports(request.capability, artifact.normalized_content_type):
            return self._result(request, artifact, attempt_id, ExtractionOutcome.UNSUPPORTED_CONTENT)
        try:
            payload = self._artifact_reader.read(artifact.content_reference)
        except SearchValidationError:
            return self._result(request, artifact, attempt_id, ExtractionOutcome.ARTIFACT_UNAVAILABLE)
        payload_checksum = "sha256:" + hashlib.sha256(payload).hexdigest()
        if (
            artifact.content_length != len(payload)
            or artifact.checksum is None
            or artifact.checksum.value != payload_checksum
        ):
            return self._result(
                request,
                artifact,
                attempt_id,
                ExtractionOutcome.MALFORMED_CONTENT,
                limitations=("artifact-content-correspondence-mismatch",),
            )

        transport_charset = self._transport_charset(artifact.reported_content_type)
        html_charset: str | None = None
        limitations = ["extracted-content-is-not-trusted-instructions"]
        if request.capability is ExtractionCapability.HTML_TO_TEXT:
            metadata_parser = _StructuralHTMLParser()
            metadata_parser.feed(payload.decode("latin-1"))
            metadata_parser.close()
            html_charset = metadata_parser.declared_charset
        used_charset, charset_source, charset_limitations = self._select_charset(
            transport_charset, html_charset
        )
        limitations.extend(charset_limitations)
        try:
            decoded = payload.decode(used_charset, errors="strict")
        except UnicodeDecodeError:
            return self._result(
                request,
                artifact,
                attempt_id,
                ExtractionOutcome.DECODING_FAILED,
                transport_charset=transport_charset,
                html_charset=html_charset,
                used_charset=used_charset,
                charset_source=charset_source,
                limitations=tuple(limitations),
            )

        if request.capability is ExtractionCapability.PLAIN_TEXT:
            text = decoded
        else:
            parser = _StructuralHTMLParser()
            parser.feed(decoded)
            parser.close()
            text = self._normalize_html_text(parser.parts)
            limitations.append("extracted-text-is-not-main-article-content")
            if parser.declared_language:
                limitations.append(f"declared-language:{parser.declared_language}")
            if parser.tolerant_recovery:
                limitations.append("html-tolerant-parsing")

        observed_length = len(text)
        deterministic_limitations = tuple(sorted(set(limitations)))
        if observed_length == 0:
            return self._result(
                request, artifact, attempt_id, ExtractionOutcome.EMPTY,
                transport_charset=transport_charset, html_charset=html_charset,
                used_charset=used_charset, charset_source=charset_source,
                observed_length=0, delivered_length=0, limitations=deterministic_limitations,
            )
        if observed_length > self._config.maximum_characters:
            return self._result(
                request, artifact, attempt_id, ExtractionOutcome.OUTPUT_TOO_LARGE,
                transport_charset=transport_charset, html_charset=html_charset,
                used_charset=used_charset, charset_source=charset_source,
                observed_length=observed_length, delivered_length=0,
                limitations=deterministic_limitations,
            )
        return self._success(
            request, artifact, attempt_id, text, transport_charset, html_charset,
            used_charset, charset_source, deterministic_limitations,
        )

    @staticmethod
    def _validate_correspondence(
        request: ExtractionRequestV1, artifact: RetrievedArtifactV1
    ) -> None:
        if (
            artifact.outcome is not RetrievalOutcome.RETRIEVED
            or request.artifact_id != artifact.artifact_id
            or request.retrieval_request_id != artifact.retrieval_request_id
            or request.correlation != artifact.provenance.correlation
        ):
            raise SearchValidationError("extraction request does not correspond to artifact")
        if request.occurrence.occurred_at < artifact.retrieval_occurrence.occurred_at:
            raise SearchValidationError("extraction request is stale relative to artifact")

    @staticmethod
    def _supports(capability: ExtractionCapability, media_type: str | None) -> bool:
        return (capability is ExtractionCapability.PLAIN_TEXT and media_type == "text/plain") or (
            capability is ExtractionCapability.HTML_TO_TEXT and media_type == "text/html"
        )

    @staticmethod
    def _transport_charset(content_type: str | None) -> str | None:
        if content_type is None:
            return None
        match = _CHARSET_PARAMETER.search(content_type)
        return match.group(1) if match else None

    @staticmethod
    def _valid_charset(value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return codecs.lookup(value).name
        except LookupError:
            return None

    @classmethod
    def _select_charset(
        cls, transport: str | None, html: str | None
    ) -> tuple[str, CharsetSource, tuple[str, ...]]:
        transport_valid = cls._valid_charset(transport)
        html_valid = cls._valid_charset(html)
        limitations: list[str] = []
        if transport is not None and transport_valid is None:
            limitations.append("invalid-transport-charset")
        if html is not None and html_valid is None:
            limitations.append("invalid-html-charset")
        if transport_valid is not None:
            if html_valid is not None and html_valid != transport_valid:
                limitations.append("transport-html-charset-conflict")
            return transport_valid, CharsetSource.TRANSPORT, tuple(limitations)
        if html_valid is not None:
            return html_valid, CharsetSource.HTML, tuple(limitations)
        limitations.append("utf8-fallback")
        return "utf-8", CharsetSource.UTF8_FALLBACK, tuple(limitations)

    @staticmethod
    def _normalize_html_text(parts: list[str]) -> str:
        joined = "".join(parts).replace("\r\n", "\n").replace("\r", "\n")
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in joined.split("\n")]
        output: list[str] = []
        for line in lines:
            if line:
                output.append(line)
            elif output and output[-1] != "":
                output.append("")
        return "\n".join(output).strip()

    def _success(
        self,
        request: ExtractionRequestV1,
        artifact: RetrievedArtifactV1,
        attempt_id: ExtractionAttemptId,
        text: str,
        transport_charset: str | None,
        html_charset: str | None,
        used_charset: str,
        charset_source: CharsetSource,
        limitations: tuple[str, ...],
    ) -> ExtractedContentV1:
        text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        reference = ExtractedContentReference(f"extracted-text:sha256-{text_digest}")
        self._content_store.put(reference, text)
        checksum = ExtractedContentChecksum("sha256:" + text_digest)
        try:
            return self._result(
                request, artifact, attempt_id, ExtractionOutcome.EXTRACTED,
                content_reference=reference, content_checksum=checksum,
                transport_charset=transport_charset, html_charset=html_charset,
                used_charset=used_charset, charset_source=charset_source,
                observed_length=len(text), delivered_length=len(text), limitations=limitations,
            )
        except Exception:
            self._content_store.release(reference)
            raise

    def _result(
        self,
        request: ExtractionRequestV1,
        artifact: RetrievedArtifactV1,
        attempt_id: ExtractionAttemptId,
        outcome: ExtractionOutcome,
        *,
        content_reference: ExtractedContentReference | None = None,
        content_checksum: ExtractedContentChecksum | None = None,
        transport_charset: str | None = None,
        html_charset: str | None = None,
        used_charset: str | None = None,
        charset_source: CharsetSource | None = None,
        observed_length: int | None = None,
        delivered_length: int | None = None,
        limitations: tuple[str, ...] = (),
    ) -> ExtractedContentV1:
        provenance = ExtractionProvenance(
            artifact.provenance.search_request_id,
            artifact.source_result_id,
            artifact.retrieval_request_id,
            artifact.artifact_id,
            request.extraction_request_id,
            attempt_id,
            _EXTRACTOR,
            request.correlation,
        )
        value = ExtractedContentV1(
            ExtractedContentId(f"search-extracted-content:{self._token(request, attempt_id)}"),
            request.extraction_request_id,
            attempt_id,
            artifact.artifact_id,
            request.capability,
            outcome,
            _EXTRACTOR,
            TEXT_EXTRACTION_ADAPTER_VERSION,
            SearchOccurrence(max(datetime.now(UTC), request.occurrence.occurred_at)),
            provenance,
            content_reference,
            content_checksum,
            transport_charset,
            html_charset,
            used_charset,
            charset_source,
            observed_length,
            delivered_length,
            False,
            limitations,
        )
        value.validate_correspondence(request, artifact)
        return value

    @staticmethod
    def _token(request: ExtractionRequestV1, attempt_id: ExtractionAttemptId) -> str:
        return hashlib.sha256(
            f"{request.extraction_request_id.value}\x1f{attempt_id.value}".encode()
        ).hexdigest()[:32]
