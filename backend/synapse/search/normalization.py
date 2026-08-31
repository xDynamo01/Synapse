"""Deterministic URL normalization, factual deduplication and ranking projections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .canonical import SEARCH_CANONICAL_FORMAT_V1, canonical_json, semantic_fingerprint
from .errors import SearchValidationError
from .identities import SearchFingerprint, SearchResultId, SearchResultSetId
from .results import NormalizedSearchResultV1, SearchResultProvenance, SearchResultSetV1

URL_NORMALIZATION_RULES_V1 = "search-url-normalization-v1"
SEARCH_DEDUP_VIEW_FORMAT_V1 = "search-dedup-view-v1"
TRACKING_PARAMETER_POLICY_V1 = "search-tracking-parameters-v1"
TRACKING_PARAMETER_NAMES_V1 = frozenset({"fbclid", "gclid"})
TRACKING_PARAMETER_PREFIXES_V1 = ("utm_",)

_URL = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://(?P<authority>[^/?#]*)"
    r"(?P<path>/[^?#]*)?(?:\?(?P<query>[^#]*))?(?:#(?P<fragment>.*))?$"
)
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_PERCENT = re.compile(r"%([0-9A-Fa-f]{2})")
_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


class UrlNormalizationError(SearchValidationError):
    """A safe URL normalization failure with no network or provider payload."""


class UrlNormalizationWarning(StrEnum):
    PROVIDER_CANONICAL_UNVERIFIED = "provider_canonical_unverified"
    NON_ROOT_TRAILING_SLASH_PRESERVED = "non_root_trailing_slash_preserved"
    QUERY_ORDER_NORMALIZED = "query_order_normalized"


class UrlComponentChange(StrEnum):
    SCHEME_CASE = "scheme_case"
    HOST_CASE_OR_IDNA = "host_case_or_idna"
    DEFAULT_PORT = "default_port"
    ROOT_PATH = "root_path"
    FRAGMENT = "fragment"
    PERCENT_ENCODING = "percent_encoding"
    QUERY_ORDER = "query_order"
    TRACKING_PARAMETERS = "tracking_parameters"


class DuplicateClassification(StrEnum):
    UNIQUE = "unique"
    EXACT_ORIGINAL_URL_DUPLICATE = "exact_original_url_duplicate"
    NORMALIZED_URL_DUPLICATE = "normalized_url_duplicate"
    PROVIDER_CANONICAL_DUPLICATE = "provider_canonical_duplicate"
    SAME_DOMAIN_ONLY = "same_domain_only"
    NOT_COMPARABLE = "not_comparable"


class RepresentativeSelectionRule(StrEnum):
    RANK_POSITION_ID_V1 = "lowest_normalized_rank_then_provider_position_then_result_id_v1"


def _normalize_percent_encoding(value: str) -> str:
    cursor = 0
    output: list[str] = []
    while cursor < len(value):
        if value[cursor] != "%":
            output.append(value[cursor])
            cursor += 1
            continue
        match = _PERCENT.match(value, cursor)
        if match is None:
            raise UrlNormalizationError("URL contains malformed percent encoding")
        byte = int(match.group(1), 16)
        character = chr(byte)
        output.append(character if character in _UNRESERVED else f"%{byte:02X}")
        cursor += 3
    return "".join(output)


def _host_and_port(authority: str, scheme: str) -> tuple[str, str | None]:
    if not authority or "@" in authority:
        raise UrlNormalizationError("URL authority is missing or contains embedded credentials")
    if authority.startswith("["):
        raise UrlNormalizationError("IP-literal hosts are unsupported by normalization V1")
    parsed_host, separator, parsed_port = authority.rpartition(":")
    host: str
    port: str | None
    if not separator:
        host, port = authority, None
    else:
        host, port = parsed_host, parsed_port
        if not port.isdigit():
            raise UrlNormalizationError("URL port must be numeric")
    if port is not None and not 1 <= int(port) <= 65535:
        raise UrlNormalizationError("URL port is outside the valid range")
    try:
        ascii_host = host.lower().removesuffix(".").encode("idna").decode("ascii")
    except UnicodeError as error:
        raise UrlNormalizationError("URL hostname cannot be normalized deterministically") from error
    labels = ascii_host.split(".")
    if len(labels) < 2 or len(ascii_host) > 253 or any(
        _HOST_LABEL.fullmatch(label) is None for label in labels
    ):
        raise UrlNormalizationError("URL hostname is malformed")
    if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
        port = None
    return ascii_host, port


def _is_tracking_parameter(normalized_key: str) -> bool:
    key = normalized_key.lower()
    return key in TRACKING_PARAMETER_NAMES_V1 or key.startswith(TRACKING_PARAMETER_PREFIXES_V1)


def _normalize_query(query: str) -> tuple[str, bool, bool, bool]:
    if not query:
        return "", False, False, False
    preserved: list[tuple[str, str, int]] = []
    removed_tracking = False
    percent_changed = False
    for index, component in enumerate(query.split("&")):
        key, separator, value = component.partition("=")
        normalized_key = _normalize_percent_encoding(key)
        normalized_value = _normalize_percent_encoding(value)
        percent_changed = percent_changed or normalized_key != key or normalized_value != value
        if _is_tracking_parameter(normalized_key):
            removed_tracking = True
            continue
        normalized_component = normalized_key + (separator + normalized_value if separator else "")
        preserved.append((normalized_key, normalized_component, index))
    ordered = sorted(preserved, key=lambda item: (item[0], item[2]))
    order_changed = [item[2] for item in ordered] != [item[2] for item in preserved]
    return "&".join(item[1] for item in ordered), removed_tracking, order_changed, percent_changed


@dataclass(frozen=True, slots=True)
class NormalizedUrlV1:
    original_url: str
    search_normalized_url: str
    normalized_url_fingerprint: SearchFingerprint
    hostname: str
    rules_version: str
    tracking_policy_version: str
    changed_components: tuple[UrlComponentChange, ...]
    warnings: tuple[UrlNormalizationWarning, ...]
    provider_canonical_url: str | None = None

    def __post_init__(self) -> None:
        expected = semantic_fingerprint(
            {"rules_version": self.rules_version, "url": self.search_normalized_url}
        )
        if self.normalized_url_fingerprint != expected:
            raise UrlNormalizationError("normalized URL fingerprint does not correspond to its value")
        if self.rules_version != URL_NORMALIZATION_RULES_V1:
            raise UrlNormalizationError("unsupported URL normalization rules")
        if self.tracking_policy_version != TRACKING_PARAMETER_POLICY_V1:
            raise UrlNormalizationError("unsupported tracking-parameter policy")

    def semantic_content(self) -> dict[str, object]:
        return {
            "rules_version": self.rules_version,
            "tracking_policy_version": self.tracking_policy_version,
            "search_normalized_url": self.search_normalized_url,
            "hostname": self.hostname,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json(
            {
                "canonical_format": SEARCH_CANONICAL_FORMAT_V1,
                "normalization": self,
                "semantic_fingerprint": self.semantic_fingerprint,
            }
        )


def normalize_search_url(
    original_url: str, *, provider_canonical_url: str | None = None
) -> NormalizedUrlV1:
    if not isinstance(original_url, str) or len(original_url) > 2048:
        raise UrlNormalizationError("URL must be bounded text")
    if any(ord(character) < 32 or ord(character) == 127 or character.isspace() for character in original_url):
        raise UrlNormalizationError("URL cannot contain control characters or whitespace")
    match = _URL.fullmatch(original_url)
    if match is None:
        raise UrlNormalizationError("URL is structurally malformed")
    original_scheme = match.group("scheme")
    scheme = original_scheme.lower()
    if scheme not in {"http", "https"}:
        raise UrlNormalizationError("URL scheme is unsupported for web Search")
    authority = match.group("authority")
    hostname, port = _host_and_port(authority, scheme)
    path = match.group("path") or ""
    normalized_path = _normalize_percent_encoding(path)
    if normalized_path == "/":
        normalized_path = ""
    query, removed_tracking, order_changed, query_percent_changed = _normalize_query(
        match.group("query") or ""
    )
    normalized_authority = hostname + (f":{port}" if port is not None else "")
    normalized = f"{scheme}://{normalized_authority}{normalized_path}"
    if query:
        normalized += f"?{query}"

    changes: set[UrlComponentChange] = set()
    if original_scheme != scheme:
        changes.add(UrlComponentChange.SCHEME_CASE)
    original_host = authority.rpartition(":")[0] if authority.rpartition(":")[1] else authority
    if original_host != hostname:
        changes.add(UrlComponentChange.HOST_CASE_OR_IDNA)
    if port is None and authority.endswith((":80", ":443")):
        changes.add(UrlComponentChange.DEFAULT_PORT)
    if path == "/":
        changes.add(UrlComponentChange.ROOT_PATH)
    if match.group("fragment") is not None:
        changes.add(UrlComponentChange.FRAGMENT)
    if normalized_path != path or query_percent_changed:
        changes.add(UrlComponentChange.PERCENT_ENCODING)
    if removed_tracking:
        changes.add(UrlComponentChange.TRACKING_PARAMETERS)
    if order_changed:
        changes.add(UrlComponentChange.QUERY_ORDER)

    warnings: set[UrlNormalizationWarning] = set()
    if provider_canonical_url is not None:
        warnings.add(UrlNormalizationWarning.PROVIDER_CANONICAL_UNVERIFIED)
    if normalized_path not in {"", "/"} and normalized_path.endswith("/"):
        warnings.add(UrlNormalizationWarning.NON_ROOT_TRAILING_SLASH_PRESERVED)
    if order_changed:
        warnings.add(UrlNormalizationWarning.QUERY_ORDER_NORMALIZED)
    fingerprint = semantic_fingerprint(
        {"rules_version": URL_NORMALIZATION_RULES_V1, "url": normalized}
    )
    return NormalizedUrlV1(
        original_url=original_url,
        search_normalized_url=normalized,
        normalized_url_fingerprint=fingerprint,
        hostname=hostname,
        rules_version=URL_NORMALIZATION_RULES_V1,
        tracking_policy_version=TRACKING_PARAMETER_POLICY_V1,
        changed_components=tuple(sorted(changes, key=lambda item: item.value)),
        warnings=tuple(sorted(warnings, key=lambda item: item.value)),
        provider_canonical_url=provider_canonical_url,
    )


@dataclass(frozen=True, slots=True)
class ResultUrlNormalization:
    result_id: SearchResultId
    normalization: NormalizedUrlV1


@dataclass(frozen=True, slots=True)
class UrlComparison:
    first_result_id: SearchResultId
    second_result_id: SearchResultId
    classification: DuplicateClassification

    def __post_init__(self) -> None:
        if self.first_result_id >= self.second_result_id:
            raise SearchValidationError("URL comparison identities must use canonical order")


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    group_fingerprint: SearchFingerprint
    classification: DuplicateClassification
    member_result_ids: tuple[SearchResultId, ...]
    representative_result_id: SearchResultId
    representative_rule: RepresentativeSelectionRule
    provider_positions: tuple[int, ...]
    search_normalized_urls: tuple[str, ...]
    provenance: tuple[SearchResultProvenance, ...]

    def __post_init__(self) -> None:
        if self.classification not in {
            DuplicateClassification.EXACT_ORIGINAL_URL_DUPLICATE,
            DuplicateClassification.NORMALIZED_URL_DUPLICATE,
            DuplicateClassification.PROVIDER_CANONICAL_DUPLICATE,
        }:
            raise SearchValidationError("duplicate group requires a duplicate classification")
        if len(self.member_result_ids) < 2 or len(set(self.member_result_ids)) != len(
            self.member_result_ids
        ):
            raise SearchValidationError("duplicate group requires unique members")
        if self.representative_result_id not in self.member_result_ids:
            raise SearchValidationError("duplicate representative must be a group member")
        if not (
            len(self.member_result_ids)
            == len(self.provider_positions)
            == len(self.search_normalized_urls)
            == len(self.provenance)
        ):
            raise SearchValidationError("duplicate group facts are inconsistent")

    def semantic_content(self) -> dict[str, object]:
        return {
            "group_fingerprint": self.group_fingerprint,
            "classification": self.classification,
            "member_result_ids": self.member_result_ids,
            "representative_result_id": self.representative_result_id,
            "representative_rule": self.representative_rule,
            "provider_positions": self.provider_positions,
            "search_normalized_urls": self.search_normalized_urls,
            "provenance": tuple(item.semantic_fingerprint for item in self.provenance),
        }


@dataclass(frozen=True, slots=True)
class RankedResultReference:
    result_id: SearchResultId
    normalized_rank: int
    provider_position: int
    duplicate_group_fingerprint: SearchFingerprint | None = None
    is_duplicate_representative: bool = False

    def __post_init__(self) -> None:
        if self.normalized_rank < 1 or self.provider_position < 1:
            raise SearchValidationError("ranked result positions must be positive")


@dataclass(frozen=True, slots=True)
class DeduplicatedSearchViewV1:
    source_result_set_id: SearchResultSetId
    source_result_set_fingerprint: SearchFingerprint
    normalizations: tuple[ResultUrlNormalization, ...]
    comparisons: tuple[UrlComparison, ...]
    duplicate_groups: tuple[DuplicateGroup, ...]
    full_ranked_view: tuple[RankedResultReference, ...]
    deduplicated_ranked_view: tuple[RankedResultReference, ...]
    format_version: str = SEARCH_DEDUP_VIEW_FORMAT_V1

    def __post_init__(self) -> None:
        for view in (self.full_ranked_view, self.deduplicated_ranked_view):
            if [item.normalized_rank for item in view] != list(range(1, len(view) + 1)):
                raise SearchValidationError("ranked view must be ordered, contiguous and gapless")
        if self.format_version != SEARCH_DEDUP_VIEW_FORMAT_V1:
            raise SearchValidationError("unsupported Search dedup view format")

    def semantic_content(self) -> dict[str, object]:
        return {
            "format": self.format_version,
            "source_result_set_fingerprint": self.source_result_set_fingerprint,
            "normalizations": tuple(
                {
                    "result_id": item.result_id,
                    "normalization": item.normalization.semantic_content(),
                    "provider_canonical_url": item.normalization.provider_canonical_url,
                }
                for item in self.normalizations
            ),
            "comparisons": self.comparisons,
            "duplicate_groups": tuple(item.semantic_content() for item in self.duplicate_groups),
            "full_ranked_view": self.full_ranked_view,
            "deduplicated_ranked_view": self.deduplicated_ranked_view,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json(
            {
                "canonical_format": SEARCH_CANONICAL_FORMAT_V1,
                "deduplicated_view": self,
                "semantic_fingerprint": self.semantic_fingerprint,
            }
        )


def _comparison(
    first: NormalizedSearchResultV1,
    second: NormalizedSearchResultV1,
    first_url: NormalizedUrlV1,
    second_url: NormalizedUrlV1,
) -> DuplicateClassification:
    if first.source_url == second.source_url:
        return DuplicateClassification.EXACT_ORIGINAL_URL_DUPLICATE
    if first_url.search_normalized_url == second_url.search_normalized_url:
        return DuplicateClassification.NORMALIZED_URL_DUPLICATE
    if first.canonical_url is not None and second.canonical_url is not None:
        first_canonical = normalize_search_url(first.canonical_url).search_normalized_url
        second_canonical = normalize_search_url(second.canonical_url).search_normalized_url
        if first_canonical == second_canonical:
            return DuplicateClassification.PROVIDER_CANONICAL_DUPLICATE
    if first_url.hostname == second_url.hostname:
        return DuplicateClassification.SAME_DOMAIN_ONLY
    return DuplicateClassification.UNIQUE


def build_deduplicated_view(result_set: SearchResultSetV1) -> DeduplicatedSearchViewV1:
    """Build a separate immutable projection; never mutate or discard source facts."""

    ordered_results = tuple(
        sorted(result_set.results, key=lambda item: (item.normalized_rank, item.provider_position, item.result_id))
    )
    normalized = {
        item.result_id: normalize_search_url(
            item.source_url, provider_canonical_url=item.canonical_url
        )
        for item in ordered_results
    }
    comparisons: list[UrlComparison] = []
    duplicate_edges: list[tuple[SearchResultId, SearchResultId, DuplicateClassification]] = []
    for index, first in enumerate(ordered_results):
        for second in ordered_results[index + 1 :]:
            classification = _comparison(
                first, second, normalized[first.result_id], normalized[second.result_id]
            )
            first_id, second_id = sorted((first.result_id, second.result_id))
            comparisons.append(UrlComparison(first_id, second_id, classification))
            if classification in {
                DuplicateClassification.EXACT_ORIGINAL_URL_DUPLICATE,
                DuplicateClassification.NORMALIZED_URL_DUPLICATE,
                DuplicateClassification.PROVIDER_CANONICAL_DUPLICATE,
            }:
                duplicate_edges.append((first_id, second_id, classification))

    parent = {item.result_id: item.result_id for item in ordered_results}

    def root(identity: SearchResultId) -> SearchResultId:
        while parent[identity] != identity:
            identity = parent[identity]
        return identity

    for first_id, second_id, _ in duplicate_edges:
        first_root, second_root = root(first_id), root(second_id)
        if first_root != second_root:
            parent[max(first_root, second_root)] = min(first_root, second_root)

    groups_by_root: dict[SearchResultId, list[NormalizedSearchResultV1]] = {}
    for item in ordered_results:
        groups_by_root.setdefault(root(item.result_id), []).append(item)
    edge_reasons = {(first, second): reason for first, second, reason in duplicate_edges}
    groups: list[DuplicateGroup] = []
    membership: dict[SearchResultId, DuplicateGroup] = {}
    for members in groups_by_root.values():
        if len(members) < 2:
            continue
        members = sorted(
            members, key=lambda item: (item.normalized_rank, item.provider_position, item.result_id)
        )
        member_ids = tuple(sorted(item.result_id for item in members))
        reasons = {
            reason
            for (first_id, second_id), reason in edge_reasons.items()
            if first_id in member_ids and second_id in member_ids
        }
        reason = min(reasons, key=lambda item: item.value)
        representative = members[0]
        fingerprint = semantic_fingerprint(
            {"members": member_ids, "reason": reason, "rule": RepresentativeSelectionRule.RANK_POSITION_ID_V1}
        )
        by_identity = sorted(members, key=lambda item: item.result_id)
        group = DuplicateGroup(
            group_fingerprint=fingerprint,
            classification=reason,
            member_result_ids=member_ids,
            representative_result_id=representative.result_id,
            representative_rule=RepresentativeSelectionRule.RANK_POSITION_ID_V1,
            provider_positions=tuple(item.provider_position for item in by_identity),
            search_normalized_urls=tuple(
                normalized[item.result_id].search_normalized_url for item in by_identity
            ),
            provenance=tuple(item.provenance for item in by_identity),
        )
        groups.append(group)
        membership.update({item.result_id: group for item in members})

    groups.sort(key=lambda item: item.member_result_ids)
    full_view = tuple(
        RankedResultReference(
            result_id=item.result_id,
            normalized_rank=index,
            provider_position=item.provider_position,
            duplicate_group_fingerprint=(membership[item.result_id].group_fingerprint if item.result_id in membership else None),
            is_duplicate_representative=(
                item.result_id in membership
                and membership[item.result_id].representative_result_id == item.result_id
            ),
        )
        for index, item in enumerate(ordered_results, start=1)
    )
    representatives = tuple(
        item
        for item in ordered_results
        if item.result_id not in membership
        or membership[item.result_id].representative_result_id == item.result_id
    )
    deduplicated_view = tuple(
        RankedResultReference(
            result_id=item.result_id,
            normalized_rank=index,
            provider_position=item.provider_position,
            duplicate_group_fingerprint=(membership[item.result_id].group_fingerprint if item.result_id in membership else None),
            is_duplicate_representative=item.result_id in membership,
        )
        for index, item in enumerate(representatives, start=1)
    )
    return DeduplicatedSearchViewV1(
        source_result_set_id=result_set.result_set_id,
        source_result_set_fingerprint=result_set.semantic_fingerprint,
        normalizations=tuple(
            ResultUrlNormalization(item.result_id, normalized[item.result_id])
            for item in sorted(ordered_results, key=lambda result: result.result_id)
        ),
        comparisons=tuple(sorted(comparisons, key=lambda item: (item.first_result_id, item.second_result_id))),
        duplicate_groups=tuple(groups),
        full_ranked_view=full_view,
        deduplicated_ranked_view=deduplicated_view,
    )
