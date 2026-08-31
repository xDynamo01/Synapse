"""Concrete Search adapters; never imported by the Search domain."""

from .config import SearXNGAdapterConfig, SearXNGCategoryMapping
from .http_retrieval import (
    HTTP_RETRIEVAL_ADAPTER_VERSION,
    HttpRetrievalAdapter,
    HttpRetrievalAdapterConfig,
    HttpRetrievalHealth,
    TransientArtifactContentStore,
)
from .searxng import (
    SEARXNG_ADAPTER_VERSION,
    SearXNGAdapter,
    SearXNGTransportError,
    SearXNGTransportMalformed,
    SearXNGTransportPort,
    SearXNGTransportRequest,
    SearXNGTransportResponse,
    SearXNGTransportResponseTooLarge,
    SearXNGTransportTimeout,
    SearXNGTransportUnavailable,
)
from .searxng_transport import (
    SEARXNG_HTTP_TRANSPORT_VERSION,
    SearXNGHttpTransport,
    SearXNGHttpTransportConfig,
    SearXNGTransportHealth,
)
from .sqlite_persistence import (
    SEARCH_SQLITE_MIGRATION_CHECKSUM_V1,
    SEARCH_SQLITE_MIGRATION_ID_V1,
    SearchSQLiteConfig,
    SearchSQLiteDatabase,
    SQLiteExtractionCacheStore,
    SQLiteRetrievalCacheStore,
    SQLiteSearchCacheStore,
    SQLiteSearchMetadataStore,
)
from .text_extraction import (
    TEXT_EXTRACTION_ADAPTER_VERSION,
    TextExtractionAdapter,
    TextExtractionAdapterConfig,
    TextExtractionHealth,
    TransientExtractedContentStore,
)

__all__ = [
    "HTTP_RETRIEVAL_ADAPTER_VERSION",
    "SEARXNG_ADAPTER_VERSION",
    "SEARCH_SQLITE_MIGRATION_CHECKSUM_V1",
    "SEARCH_SQLITE_MIGRATION_ID_V1",
    "TEXT_EXTRACTION_ADAPTER_VERSION",
    "HttpRetrievalAdapter",
    "HttpRetrievalAdapterConfig",
    "HttpRetrievalHealth",
    "SearXNGAdapter",
    "SearXNGAdapterConfig",
    "SearXNGCategoryMapping",
    "SearXNGTransportPort",
    "SearXNGTransportRequest",
    "SearXNGTransportResponse",
    "SearXNGTransportError",
    "SearXNGTransportMalformed",
    "SearXNGTransportResponseTooLarge",
    "SearXNGTransportTimeout",
    "SearXNGTransportUnavailable",
    "SEARXNG_HTTP_TRANSPORT_VERSION",
    "SearXNGHttpTransport",
    "SearXNGHttpTransportConfig",
    "SearXNGTransportHealth",
    "SQLiteExtractionCacheStore",
    "SQLiteRetrievalCacheStore",
    "SQLiteSearchCacheStore",
    "SQLiteSearchMetadataStore",
    "SearchSQLiteConfig",
    "SearchSQLiteDatabase",
    "TextExtractionAdapter",
    "TextExtractionAdapterConfig",
    "TextExtractionHealth",
    "TransientArtifactContentStore",
    "TransientExtractedContentStore",
]
