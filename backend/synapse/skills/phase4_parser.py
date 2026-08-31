from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar, cast

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode
from yaml.tokens import (
    AliasToken,
    AnchorToken,
    BlockEndToken,
    BlockMappingStartToken,
    BlockSequenceStartToken,
    DocumentStartToken,
    FlowMappingEndToken,
    FlowMappingStartToken,
    FlowSequenceEndToken,
    FlowSequenceStartToken,
    ScalarToken,
    TagToken,
)

from synapse.skills.phase2_errors import SkillPhase2DomainError
from synapse.skills.phase2_models import (
    PublishedSkillManifest,
    SkillCompatibilityDeclaration,
    SkillContentKind,
    SkillContentRef,
    SkillProvenance,
    SkillPublicationScope,
    SkillSecurityDeclaration,
)
from synapse.skills.phase2_values import (
    SkillContentFingerprint,
    SkillId,
    SkillLogicalPath,
    SkillManifestFormatVersion,
    SkillSemanticReference,
    SkillVersion,
)
from synapse.skills.phase4_errors import (
    DuplicateSkillManifestKey,
    InvalidRawSkillManifest,
    MissingSkillManifestField,
    SkillVerificationResourceLimitExceeded,
    UnknownSkillManifestField,
    UnsafeSkillManifestTag,
    UnsupportedSkillManifestFeature,
)
from synapse.skills.phase4_models import SkillVerificationPolicy

_T = TypeVar("_T")
_STR_TAG = "tag:yaml.org,2002:str"
_INT_TAG = "tag:yaml.org,2002:int"
_BOOL_TAG = "tag:yaml.org,2002:bool"
_NULL_TAG = "tag:yaml.org,2002:null"
_TOP_REQUIRED = {
    "format_version",
    "skill_id",
    "version",
    "display_name",
    "summary",
    "description",
    "provenance",
    "scopes",
    "content",
}
_TOP_OPTIONAL = {"compatibility", "security"}


def parse_published_skill_manifest(
    raw: bytes,
    *,
    policy: SkillVerificationPolicy | None = None,
) -> PublishedSkillManifest:
    """Parse strict UTF-8 bytes as the non-extensible Phase 2 YAML subset."""
    selected = policy or SkillVerificationPolicy()
    if not isinstance(raw, bytes):
        raise InvalidRawSkillManifest()
    if len(raw) > selected.max_manifest_bytes:
        raise SkillVerificationResourceLimitExceeded()
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise InvalidRawSkillManifest() from None
    try:
        _preflight_yaml(text, selected)
        documents = iter(yaml.compose_all(text, Loader=yaml.SafeLoader))
        document = next(documents, None)
        if next(documents, None) is not None:
            raise UnsupportedSkillManifestFeature()
    except (UnsafeSkillManifestTag, UnsupportedSkillManifestFeature):
        raise
    except yaml.YAMLError:
        raise InvalidRawSkillManifest() from None
    if document is None:
        raise InvalidRawSkillManifest()
    value = _node_value(document, selected, depth=0, counter=[0])
    root = _mapping(value)
    _fields(root, required=_TOP_REQUIRED, optional=_TOP_OPTIONAL)
    try:
        content = tuple(_content(item) for item in _sequence(root["content"]))
        if len(content) > selected.max_declarations:
            raise SkillVerificationResourceLimitExceeded()
        return PublishedSkillManifest(
            format_version=SkillManifestFormatVersion(_integer(root["format_version"])),
            skill_id=SkillId(_string(root["skill_id"])),
            version=SkillVersion.parse(_string(root["version"])),
            display_name=_string(root["display_name"]),
            summary=_string(root["summary"]),
            description=_string(root["description"]),
            provenance=_provenance(root["provenance"]),
            scopes=tuple(
                SkillPublicationScope(_string(item))
                for item in _sequence(root["scopes"])
            ),
            content=content,
            compatibility=_empty_object(
                root.get("compatibility"), SkillCompatibilityDeclaration
            ),
            security=_empty_object(root.get("security"), SkillSecurityDeclaration),
        )
    except SkillVerificationResourceLimitExceeded:
        raise
    except (SkillPhase2DomainError, TypeError, ValueError, KeyError):
        raise InvalidRawSkillManifest() from None


def _preflight_yaml(text: str, policy: SkillVerificationPolicy) -> None:
    depth = 0
    documents = 0
    for count, token in enumerate(yaml.scan(text, Loader=yaml.SafeLoader), start=1):
        if count > policy.max_yaml_tokens:
            raise SkillVerificationResourceLimitExceeded()
        if isinstance(token, TagToken):
            raise UnsafeSkillManifestTag()
        if isinstance(token, (AnchorToken, AliasToken)):
            raise UnsupportedSkillManifestFeature()
        if isinstance(token, DocumentStartToken):
            documents += 1
            if documents > 1:
                raise UnsupportedSkillManifestFeature()
        if isinstance(token, ScalarToken) and len(token.value) > policy.max_scalar_chars:
            raise SkillVerificationResourceLimitExceeded()
        if isinstance(
            token,
            (
                BlockMappingStartToken,
                BlockSequenceStartToken,
                FlowMappingStartToken,
                FlowSequenceStartToken,
            ),
        ):
            depth += 1
            if depth > policy.max_yaml_depth:
                raise SkillVerificationResourceLimitExceeded()
        elif isinstance(
            token,
            (BlockEndToken, FlowMappingEndToken, FlowSequenceEndToken),
        ):
            depth = max(0, depth - 1)


def _node_value(
    node: Node,
    policy: SkillVerificationPolicy,
    *,
    depth: int,
    counter: list[int],
) -> object:
    if depth > policy.max_yaml_depth:
        raise SkillVerificationResourceLimitExceeded()
    if isinstance(node, ScalarNode):
        if len(node.value) > policy.max_scalar_chars:
            raise SkillVerificationResourceLimitExceeded()
        if node.tag == _STR_TAG:
            return node.value
        if node.tag == _INT_TAG and node.value.isdecimal():
            return int(node.value)
        if node.tag == _BOOL_TAG and node.value in {"true", "false"}:
            return node.value == "true"
        if node.tag == _NULL_TAG and node.value in {"null", ""}:
            return None
        if not node.tag.startswith("tag:yaml.org,2002:"):
            raise UnsafeSkillManifestTag()
        raise UnsupportedSkillManifestFeature()
    if isinstance(node, SequenceNode):
        counter[0] += len(node.value)
        if counter[0] > policy.max_yaml_collection_items:
            raise SkillVerificationResourceLimitExceeded()
        return tuple(
            _node_value(item, policy, depth=depth + 1, counter=counter)
            for item in node.value
        )
    if isinstance(node, MappingNode):
        counter[0] += len(node.value)
        if counter[0] > policy.max_yaml_collection_items:
            raise SkillVerificationResourceLimitExceeded()
        result: dict[str, object] = {}
        for key_node, value_node in node.value:
            if not isinstance(key_node, ScalarNode) or key_node.tag != _STR_TAG:
                raise InvalidRawSkillManifest()
            if key_node.value == "<<":
                raise UnsupportedSkillManifestFeature()
            if key_node.value in result:
                raise DuplicateSkillManifestKey()
            result[key_node.value] = _node_value(
                value_node, policy, depth=depth + 1, counter=counter
            )
        return result
    raise UnsupportedSkillManifestFeature()


def _fields(
    value: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    accepted_optional = optional or set()
    if not required.issubset(value):
        raise MissingSkillManifestField()
    if not set(value).issubset(required | accepted_optional):
        raise UnknownSkillManifestField()


def _content(value: object) -> SkillContentRef:
    item = _mapping(value)
    required = {"logical_path", "fingerprint", "kind", "media_type", "size_bytes"}
    _fields(item, required=required, optional={"role"})
    role = item.get("role")
    return SkillContentRef(
        logical_path=SkillLogicalPath(_string(item["logical_path"])),
        fingerprint=SkillContentFingerprint(_string(item["fingerprint"])),
        kind=SkillContentKind(_string(item["kind"])),
        media_type=_string(item["media_type"]),
        size_bytes=_integer(item["size_bytes"]),
        role=None if role is None else SkillSemanticReference(_string(role)),
    )


def _provenance(value: object) -> SkillProvenance:
    item = _mapping(value)
    optional = {
        "source_repository_ref",
        "publication_ref",
        "source_revision_ref",
        "build_ref",
        "signature_ref",
        "lineage_ref",
    }
    _fields(item, required={"publisher_ref"}, optional=optional)
    refs = {
        name: (
            None
            if item.get(name) is None
            else SkillSemanticReference(_string(item[name]))
        )
        for name in optional
    }
    return SkillProvenance(
        publisher_ref=SkillSemanticReference(_string(item["publisher_ref"])),
        **refs,
    )


def _empty_object(value: object | None, factory: type[_T]) -> _T:
    if value is None:
        return factory()
    item = _mapping(value)
    _fields(item, required=set())
    return factory()


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise InvalidRawSkillManifest()
    return cast(Mapping[str, object], value)


def _sequence(value: object) -> Sequence[object]:
    if not isinstance(value, tuple):
        raise InvalidRawSkillManifest()
    return value


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidRawSkillManifest()
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidRawSkillManifest()
    return value
