from importlib.metadata import PackageNotFoundError, version

from ebms_adapter_client.client import EbmsAdapterClient
from ebms_adapter_client.config import EbmsAdapterClientConfig
from ebms_adapter_client.exceptions import (
    EbmsAdapterError,
    EbmsBadRequestError,
    EbmsConnectionError,
    EbmsNotFoundError,
    EbmsServerError,
)
from ebms_adapter_client.models import (
    CertificateMapping,
    DataSource,
    EbMSMessageStatus,
    Message,
    MessageEvent,
    MessageEventType,
    MessageFilter,
    MessageProperties,
    MessageRequest,
    MessageRequestProperties,
    MessageStatus,
    Party,
    URLMapping,
)

try:
    __version__ = version("ebms-adapter-client")
except PackageNotFoundError:
    # Running from source without an installed/editable metadata entry.
    __version__ = "0.0.0+unknown"

__all__ = [
    "EbmsAdapterClient",
    "EbmsAdapterClientConfig",
    "EbmsAdapterError",
    "EbmsBadRequestError",
    "EbmsConnectionError",
    "EbmsNotFoundError",
    "EbmsServerError",
    "CertificateMapping",
    "DataSource",
    "EbMSMessageStatus",
    "Message",
    "MessageEvent",
    "MessageEventType",
    "MessageFilter",
    "MessageProperties",
    "MessageRequest",
    "MessageRequestProperties",
    "MessageStatus",
    "Party",
    "URLMapping",
]
