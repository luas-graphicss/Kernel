SYNTAX = "syntax"
TOO_LARGE = "too-large"
DUPLICATE = "duplicate"
UNKNOWN_SECTION = "unknown-section"
UNKNOWN_KEY = "unknown-key"
MISSING_SECTION = "missing-section"
MISSING_KEY = "missing-key"
WRONG_TYPE = "wrong-type"
OUT_OF_RANGE = "out-of-range"
UNSUPPORTED_VERSION = "unsupported-version"
UNKNOWN_SERVICE = "unknown-service"
MISSING_SERVICE = "missing-service"
UNKNOWN_DEPENDENCY = "unknown-dependency"
MISSING_DEPENDENCY = "missing-dependency"
SELF_DEPENDENCY = "self-dependency"
DEPENDENCY_CYCLE = "dependency-cycle"
INVALID_ADDRESS = "invalid-address"
GATEWAY_OFF_LINK = "gateway-off-link"
UNKNOWN_RIGHT = "unknown-right"
PROCESS_BUDGET = "process-budget"


class ConfigurationError(Exception):
    def __init__(self, reason: str, subject: str) -> None:
        super().__init__(reason, subject)
        self.reason = reason
        self.subject = subject
