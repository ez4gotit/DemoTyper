from enum import IntEnum


class ExitCode(IntEnum):
    """Process exit codes (spec section 11)."""

    OK = 0
    VALIDATION = 1
    STEP_FAILED = 2
    ENVIRONMENT = 3
    INTERRUPTED = 130
