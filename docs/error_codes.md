# Error and Warning Codes in MLCFlow

MLCFlow uses a standardized system for error and warning codes to provide consistent error handling across the framework. This document explains the error code system and how to use it.

## Overview

The error code system consists of two main components:

1. **ErrorCode(1000-1399)**: Enum class for error codes (return > 0)
2. **WarningCode(2000-2399)**: Enum class for warning codes (return = 0, with warning_code field)

## Error Code Structure

Error codes are organized by category:

- **General errors (1000-1099)**: Common errors that can occur in any part of the system
- **Script errors (1100-1199)**: Errors specific to script execution and management
- **Repository errors (1200-1299)**: Errors related to repository operations
- **Cache errors (1300-1399)**: Errors related to cache operations

## Warning Code Structure

Warning codes follow a similar structure:

- **General warnings (2000-99)**: Common warnings that can occur in any part of the system
- **Script warnings (2100-2199)**: Warnings specific to script execution and management
- **Repository warnings (2200-2299)**: Warnings related to repository operations
- **Cache warnings (2300-2399)**: Warnings related to cache operations

## Usage

### In MLCFlow Framework

When returning an error:

```python
from mlc.error_codes import ErrorCode, get_error_message

return {'return': ErrorCode.INVALID_ARGUMENT.code, 'error': get_error_message(ErrorCode.INVALID_ARGUMENT.code)}
```

When returning a warning:

```python
from mlc.error_codes import WarningCode, get_warning_message

return {'return': 0, 'warning_code': WarningCode.EMPTY_RESULT.code, 'warning': get_warning_message(WarningCode.EMPTY_RESULT.code)}
```

### In Scripts

When checking for errors or warnings:

```python
from mlc.error_codes import is_warning_code

result = mlc_cache.access({'action': 'rm', 'target': 'cache', 'tags': cache_rm_tags, 'f': True})
if result['return'] != 0 and not is_warning_code(result['return']):
    # Handle error
    return result
```

## Helper Functions

The error code system provides several helper functions:

- `get_error_message(error_code)`: Get the description for an error code
- `get_warning_message(warning_code)`: Get the description for a warning code
- `is_warning_code(code)`: Check if a code is a warning code
- `is_error_code(code)`: Check if a code is an error code
- `get_code_type(code)`: Get the type of a code (error, warning, or unknown)

## Adding New Error or Warning Codes

To add a new error or warning code, update the appropriate enum class in `mlc/error_codes.py`:

```python
# For a new error code
NEW_ERROR = (105, "Description of the new error")

# For a new warning code
NEW_WARNING = (103, "Description of the new warning")
```

Make sure to follow the category structure and use the next available code in the appropriate range. 