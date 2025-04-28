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