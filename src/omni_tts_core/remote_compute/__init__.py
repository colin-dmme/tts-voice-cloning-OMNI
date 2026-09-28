"""Generic remote compute contracts used by Studio clients."""

from .client import BrokerClient
from .models import (
    BrokerConnectionOptions,
    JobLease,
    RemoteJobStatus,
    RemoteTtsJob,
    RemoteTtsRequest,
    RemoteTtsResultMetadata,
    WorkerCapabilities,
    WorkerModelCapability,
    WorkerProfile,
    WorkerRecord,
    WorkerRuntimeInfo,
    WorkerSelectionSettings,
)
from .profiles import WorkerProfileDocument, WorkerProfileStore

__all__ = [
    "BrokerClient",
    "BrokerConnectionOptions",
    "JobLease",
    "RemoteJobStatus",
    "RemoteTtsJob",
    "RemoteTtsRequest",
    "RemoteTtsResultMetadata",
    "WorkerCapabilities",
    "WorkerModelCapability",
    "WorkerProfile",
    "WorkerRecord",
    "WorkerProfileDocument",
    "WorkerProfileStore",
    "WorkerRuntimeInfo",
    "WorkerSelectionSettings",
]
