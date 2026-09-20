"""
core/execution/testnet/__init__.py
==================================
Milestone 20: Gate 5 Extended Testnet Reliability Qualification & Execution Lifecycle Rehearsal.
"""

from core.execution.testnet.authentication import (
    AuthenticationError,
    sign_binance_request,
    sign_bybit_v5_rest,
    sign_bybit_v5_websocket,
)
from core.execution.testnet.binance_spot import BinanceSpotTestnetAdapter
from core.execution.testnet.bybit_v5 import BybitV5TestnetAdapter
from core.execution.testnet.credential_policy import (
    CredentialPolicy,
    CredentialScopeError,
    TestnetCredentials,
    mask_secret,
)
from core.execution.testnet.endpoint_policy import (
    EndpointPolicy,
    EndpointSecurityBreachError,
    Environment,
)
from core.execution.testnet.evidence import (
    EvidenceGenerator,
    Milestone21Verdict,
)
from core.execution.testnet.recovery import (
    AuthoritativeRecoveryManager,
    UnresolvedRecoveryAnomalyError,
)
from core.execution.testnet.rest_transport import (
    BadRequestError,
    ExchangeServerError,
    RateLimitError,
    RestAuthenticationError,
    RestResponse,
    RestTransport,
    RestTransportError,
)
from core.execution.testnet.schemas import (
    BurnInState,
    ChildOrderLifecycle,
    ClockPolicy,
    DecomposedLatencyRecord,
    EconomicFillRecord,
    FaultSeverity,
    FaultType,
    LatencyQuantileSummary,
    SessionDurations,
    SessionEpoch,
    VenueCapabilities,
)
from core.execution.testnet.websocket_transport import (
    WebSocketState,
    WebSocketTransport,
)

__all__ = [
    "AuthenticationError",
    "AuthoritativeRecoveryManager",
    "BadRequestError",
    "BinanceSpotTestnetAdapter",
    "BurnInState",
    "BybitV5TestnetAdapter",
    "ChildOrderLifecycle",
    "ClockPolicy",
    "CredentialPolicy",
    "CredentialScopeError",
    "DecomposedLatencyRecord",
    "EconomicFillRecord",
    "EndpointPolicy",
    "EndpointSecurityBreachError",
    "Environment",
    "EvidenceGenerator",
    "ExchangeServerError",
    "FaultSeverity",
    "FaultType",
    "LatencyQuantileSummary",
    "Milestone21Verdict",
    "RateLimitError",
    "RestAuthenticationError",
    "RestResponse",
    "RestTransport",
    "RestTransportError",
    "SessionDurations",
    "SessionEpoch",
    "TestnetCredentials",
    "UnresolvedRecoveryAnomalyError",
    "VenueCapabilities",
    "WebSocketState",
    "WebSocketTransport",
    "mask_secret",
    "sign_binance_request",
    "sign_bybit_v5_rest",
    "sign_bybit_v5_websocket",
]
