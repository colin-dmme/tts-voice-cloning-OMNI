"""Generic remote compute contracts used by Studio clients."""

from .client import BrokerClient
from .failover import (
    FailoverDecision,
    RemoteComputeCoordinator,
    RemoteExecutionOutcome,
    choose_failover,
)
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
    "FailoverDecision",
    "JobLease",
    "RemoteJobStatus",
    "RemoteComputeCoordinator",
    "RemoteExecutionOutcome",
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
    "choose_failover",
]
