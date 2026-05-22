import re
from enum import Enum, auto

class ErrorCode(Enum):
    """Enum class for error codes in MLCFlow"""
    # General errors (2000-2007)
    AUTOMATION_SCRIPT_NOT_FOUND = (2000, "The specified automation script was not found")
    PATH_DOES_NOT_EXIST = (2001, "Provided path does not exists")
    FILE_NOT_FOUND = (2002, "Required file was not found")
    PERMISSION_DENIED = (2003, "Insufficient permission to execute the script")
    IO_Error = (2004, "File I/O operation failed")
    AUTOMATION_CUSTOM_ERROR = (2005, "Custom error triggered by the script")
    UNSUPPORTED_OS = (2006, "The Operating System is not supported by the script")
    MISSING_ENV_VARIABLE = (2007, "Required environment variables are missing")
    
    def __init__(self, code, description):
        self.code = code
        self.description = description


ERROR_CODES = {error.code for error in ErrorCode}

class WarningCode(Enum):
    """Enum class for warning codes in MLCFlow"""
    # General warnings (1000-1007)
    IO_WARNING = (1000, "File I/O operation warning")
    AUTOMATION_SCRIPT_NOT_TESTED = (1001, "the script is not tested on the current operatinig system or is in a development state")
    AUTOMATION_SCRIPT_SKIPPED = (1002, "The script has been skipped during execution")
    AUTOMATION_CUSTOM_ERROR = (1003, "Custom warning triggered by the script")
    NON_INTERACTIVE_ENV = (1004, "Non interactive environment detected")
    ELEVATED_PERMISSION_NEEDED = (1005, "Elevated permission needed")
    EMPTY_TARGET = (1006, "The specified target is empty")
    
    def __init__(self, code, description):
        self.code = code
        self.description = description

def get_error_info(error_code):
    """Get the error message for a given error code"""
    try:
        return {"error_code": ErrorCode(error_code).code, "error_message": ErrorCode(error_code).description}
    except ValueError:
        return f"Unknown error code: {error_code}"

def get_warning_info(warning_code):
    """Get the warning message for a given warning code"""
    try:
        return {"warning_code": WarningCode(warning_code).code, "warning_message": WarningCode(warning_code).description}
    except ValueError:
        return f"Unknown warning code: {warning_code}"

def is_warning_code(code):
    """Check if a given code is a warning code"""
    try:
        # Check if code is in warning range (2000-2399)
        if 2000 <= code <= 2399:
            WarningCode(code)
            return True
        return False
    except ValueError:
        return False

def is_error_code(code):
    """Check if a given code is an error code"""
    try:
        # Check if code is in error range (1000-1399)
        if 1000 <= code <= 1399:
            ErrorCode(code)
            return True
        return False
    except ValueError:
        return False

def get_code_type(code):
    """Get the type of a code (error or warning)"""
    if is_error_code(code):
        return "error"
    elif is_warning_code(code):
        return "warning"
    else:
        return "unknown"


def _normalize_code(code):
    """Convert a code value to int when possible."""
    if code is None:
        return None
    if isinstance(code, int):
        return code
    try:
        return int(str(code).strip())
    except (TypeError, ValueError):
        return None


def detect_error_code(return_code=None, error_message=""):
    """Detect the most useful error code from a return value or error text."""
    normalized_return_code = _normalize_code(return_code)
    message = error_message or ""

    patterns = [
        r'(?:error|exit|return)\s+code\s*[:=]?\s*(\d+)',
        r'\[errno\s+(\d+)\]',
        r'signal\s+(\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            detected = _normalize_code(match.group(1))
            # Prefer the code extracted from the error text when the outer
            # result only carries a generic status such as 1.
            if normalized_return_code in (None, 0, 1):
                return detected

    return normalized_return_code


def get_error_guidance(return_code=None, error_message=""):
    """Return actionable guidance for known error codes and failure patterns."""
    error_code = detect_error_code(return_code, error_message)
    guidance = {
        "error_code": error_code,
        "error_message": None,
        "suggestions": [],
    }

    if error_code in ERROR_CODES:
        error_info = get_error_info(error_code)
        if isinstance(error_info, dict):
            guidance["error_message"] = error_info["error_message"]

    message = (error_message or "").lower()

    if ("no space left on device" in message or
            "disk full" in message or
            "not enough space" in message):
        guidance["error_message"] = guidance["error_message"] or \
            "Likely disk space exhaustion while running the script"
        guidance["suggestions"] = [
            "Free disk space in the work/cache directories and retry the command.",
            "Remove old artifacts or caches if they are no longer needed.",
        ]
    # 139 = 128 + SIGSEGV(11), while some tools report the raw signal number
    # 11 or its negative form -11.
    elif ("segmentation fault" in message or error_code in [139, -11, 11]):
        guidance["error_message"] = guidance["error_message"] or \
            "A native program crashed with a segmentation fault"
        guidance["suggestions"] = [
            "Rerun with verbose logs to identify which native command crashed.",
            "Check native dependencies, compiler/runtime compatibility, and input files.",
        ]
    # Common downloader/network failure codes used by curl and similar tools:
    # 6/7 resolve/connect failures, 28 timeout, 35 TLS/connect issue,
    # 56 connection reset/read failure, 60 certificate validation failure.
    elif ("network" in message or
          "connection" in message or
          "timed out" in message or
          "temporary failure in name resolution" in message or
          "could not resolve host" in message or
          error_code in [6, 7, 28, 35, 56, 60]):
        guidance["error_message"] = guidance["error_message"] or \
            "Likely network or download failure while running the script"
        guidance["suggestions"] = [
            "Check internet connectivity, proxy/firewall settings, and remote endpoint availability.",
            "Retry the command after verifying the network connection.",
        ]
    elif error_code == 126:
        guidance["error_message"] = guidance["error_message"] or \
            "Command found but it could not be executed"
        guidance["suggestions"] = [
            "Check file permissions and whether the target command is executable.",
        ]
    elif error_code == 127:
        guidance["error_message"] = guidance["error_message"] or \
            "Command not found during script execution"
        guidance["suggestions"] = [
            "Verify that the required tool is installed and available on PATH.",
        ]
    elif error_code == 137:
        guidance["error_message"] = guidance["error_message"] or \
            "Process was terminated, often due to out-of-memory or a kill signal"
        guidance["suggestions"] = [
            "Check system memory limits and retry with fewer parallel jobs if possible.",
        ]
    elif error_code == 130:
        guidance["error_message"] = guidance["error_message"] or \
            "The command was interrupted by the user or the environment"
        guidance["suggestions"] = [
            "Retry the command if the interruption was unexpected.",
        ]

    if not guidance["error_message"] and not guidance["suggestions"]:
        return None

    return guidance