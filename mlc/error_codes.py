from enum import Enum, auto

class ErrorCode(Enum):
    """Enum class for error codes in MLCFlow"""
    # General errors (1000-1099)
    UNKNOWN_ERROR = (1000, "An unknown error occurred")
    INVALID_ARGUMENT = (1001, "Invalid argument provided")
    FILE_NOT_FOUND = (1002, "File not found")
    PERMISSION_DENIED = (1003, "Permission denied")
    INVALID_ACTION = (1004, "Invalid action specified")
    INVALID_TARGET = (1005, "Invalid target specified")
    REPO_NOT_FOUND = (1006, "Repository not found")
    ITEM_NOT_FOUND = (1007, "Item not found")
    INVALID_META = (1008, "Invalid metadata")
    INVALID_YAML = (1009, "Invalid YAML format")
    INVALID_JSON = (1010, "Invalid JSON format")
    
    # Script errors (1100-1199)
    SCRIPT_NOT_FOUND = (1100, "Script not found")
    SCRIPT_EXECUTION_FAILED = (1101, "Script execution failed")
    SCRIPT_AUTOMATION_NOT_FOUND = (1102, "Script automation not found")
    SCRIPT_MODULE_NOT_FOUND = (1103, "Script module not found")
    SCRIPT_FUNCTION_NOT_FOUND = (1104, "Script function not found")
    
    # Repository errors (1200-1299)
    REPO_META_MISSING = (1200, "Repository metadata missing")
    
    # Cache errors (1300-1399)
    CACHE_CORRUPT = (1300, "Cache is corrupt")
    
    def __init__(self, code, description):
        self.code = code
        self.description = description

class WarningCode(Enum):
    """Enum class for warning codes in MLCFlow"""
    # General warnings (2000-2099)
    UNKNOWN_WARNING = (2000, "An unknown warning occurred")
    EMPTY_RESULT = (2001, "No results found")
    MULTIPLE_RESULTS = (2002, "Multiple results found")
    INCOMPLETE_OPERATION = (2003, "Operation completed with warnings")
    
    # Script warnings (2100-2199)
    SCRIPT_DEPRECATED = (2100, "Script is deprecated")
    SCRIPT_VERSION_MISMATCH = (2101, "Script version mismatch")
    
    # Repository warnings (2200-2299)
    REPO_OUT_OF_DATE = (2200, "Repository is out of date")
    REPO_META_OUT_OF_DATE = (2201, "Repository metadata is out of date")
    
    # Cache warnings (2300-2399)
    CACHE_OUT_OF_DATE = (2300, "Cache is out of date")
    CACHE_PARTIAL = (2301, "Cache is partially complete")
    CACHE_EMPTY = (2302, "Cache is empty")
    
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