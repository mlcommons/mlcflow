import argparse
import subprocess
import re
import os
import importlib.util
import platform
import json
import yaml
import uuid
import shutil
import tarfile
import zipfile

def generate_temp_file(i):
    """
    Generate a temporary file and optionally clean up the directory.

    Args:
        i (dict): The input dictionary with the following keys:
            - (suffix) (str): Temp file suffix (default '')
            - (prefix) (str): Temp file prefix (default '')
            - (remove_dir) (bool): If True, remove the directory after file generation (default False)
            - (string) (str): Optional string content to write to the file (default '')

    Returns:
        dict: A dictionary containing:
            - return (int): Return code, 0 if no error, >0 if error
            - error (str): Error string if return > 0
            - file_name (str): The generated file name
    """
    try:
        # Retrieve arguments from input dictionary
        suffix = i.get('suffix', '')
        prefix = i.get('prefix', '')
        content = i.get('string', '')
        remove_dir = i.get('remove_dir', False)

        # Generate a unique file name using uuid
        temp_file_name = f"{prefix}{uuid.uuid4().hex}{suffix}"
        
        # Optionally write the string content to the file
        with open(temp_file_name, 'w') as temp_file:
            temp_file.write(content)
        
        # If remove_dir is True, remove the directory where the file is created
        if remove_dir:
            dir_name = os.path.dirname(temp_file_name)
            shutil.rmtree(dir_name, ignore_errors=True)

        return {'return': 0, 'file_name': temp_file_name}

    except Exception as e:
        return {'return': 1, 'error': str(e)}

def load_txt(file_name, check_if_exists=False, split=False, match_text=None, fail_if_no_match=None, remove_after_read=False):
    """
    Load text from a file with optional checks, processing, and regex matching.

    Args:
        file_name (str): Path to the file to load.
        check_if_exists (bool): If True, checks if the file exists before reading.
        split (bool): If True, splits the text into lines and returns as a list.
        match_text (str): If provided, a regular expression to search for in the file.
        fail_if_no_match (str): Error message to return if match_text is not found.
        remove_after_read (bool): If True, deletes the file after reading.

    Returns:
        dict: 
            * return (int): 0 if successful, 1 if an error occurred.
            * error (str): Error message if return > 0.
            * string (str): Loaded text if split is False.
            * lines (list): List of lines if split is True.
    """
    if check_if_exists and not os.path.isfile(file_name):
        return {'return': 1, 'error': f"File '{file_name}' does not exist."}
    
    try:
        with open(file_name, 'r') as f:
            content = f.read()
        match_ = False 
        # Check for match_text using regex
        if match_text:
            match_ = re.search(match_text, content)
            if not match_ and fail_if_no_match:
                return {'return': 1, 'error': fail_if_no_match}
        if remove_after_read:
            os.remove(file_name)
        
        result = {'return': 0}
        if split:
            result['list'] = content.splitlines()
            result['string'] = content
        else:
            result['string'] = content
        
        if match_:
            result['match'] = match_
        
        return result

    except Exception as e:
        return {'return': 1, 'error': str(e)}

def compare_versions(current_version, min_version):
    """
    Compare two semantic version strings.

    Args:
        current_version (str): The current version string (e.g., "1.2.3").
        min_version (str): The minimum required version string (e.g., "1.0.0").

    Returns:
        int: -1 if current_version < min_version,
             0 if current_version == min_version,
             1 if current_version > min_version.
    """
    try:
        # Use `packaging.version` to handle semantic version comparison
        current = version.parse(current_version)
        minimum = version.parse(min_version)

        if current < minimum:
            return -1
        elif current > minimum:
            return 1
        else:
            return 0
    except Exception as e:
        raise ValueError(f"Invalid version format: {e}")

def run_system_cmd(i):
    """
    Execute a system command in a specified path.

    Args:
        i (dict): A dictionary containing:
            - 'path' (str): The directory to run the command in.
            - 'cmd' (str): The system command to execute.

    Returns:
        dict: A dictionary with the result of the execution:
            - {'return': 0, 'output': <command_output>} on success.
            - {'return': 1, 'error': <error_message>} on failure.
    """
    # Extract path and cmd from the input dictionary
    path = i.get('path', '.')
    cmd = i.get('cmd', '')

    if not cmd:
        return {'return': 1, 'error': 'No command provided to execute.'}

    if not os.path.exists(path):
        return {'return': 1, 'error': f"Specified path does not exist: '{path}'"}

    # Change to the specified path and execute the command
    try:
        result = subprocess.run(
            cmd,
            cwd=path,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return {
            'return': 0,
            'output': result.stdout.strip(),
            'error_output': result.stderr.strip()
        }
    except subprocess.CalledProcessError as e:
        return {
            'return': 1,
            'error': f"Command execution failed with error code {e.returncode}.",
            'error_output': e.stderr.strip()
        }
    except Exception as e:
        return {'return': 1, 'error': f"Unexpected error occurred: {str(e)}"}


def print_env(env, yaml=True, sort_keys=True, begin_spaces=None):
    printd(env, yaml=yaml, sort_keys=sort_keys, begin_spaces=begin_spaces)

def printd(mydict, yaml=True, sort_keys=True, begin_spaces = None):
    if yaml:
        print_formatted_yaml(mydict, sort_keys=sort_keys, begin_spaces=begin_spaces)
    else:
        print_formatted_json(mydict, sort_keys = sort_keys, begin_spaces = begin_spaces)

def print_formatted_yaml(data, sort_keys=True, begin_spaces = None):
    """
    Converts a Python dictionary (or other serializable object) to a YAML-formatted
    string and prints it in a human-readable format.

    Args:
        data (dict or list): The data to format as YAML and print.

    Example:
        my_data = {"name": "John", "age": 30, "skills": ["Python", "ML"]}
        print_formatted_yaml(my_data)
    """
    try:
        yaml_string = yaml.dump(
            data, 
            default_flow_style=False, 
            sort_keys=False, 
            allow_unicode=True
        )
        if not begin_spaces:
            print(yaml_string)
        else:
            indented_yaml_str = "\n".join(" " * begin_spaces + line for line in yaml_string.splitlines())
            print(indented_yaml_str)
    except yaml.YAMLError as e:
        print(f"Error formatting YAML: {e}")

def print_formatted_json(data, sort_keys = True, begin_spaces = None):
    """
    Prints a dictionary as a formatted JSON string.

    Args:
        data (dict): The dictionary to format and print.

    Returns:
        None
    """
    try:
        formatted_json = json.dumps(data, indent=4, sort_keys=sort_keys)
        if not begin_spaces:
            print(formatted_json)
        else:
            indented_json_str = "\n".join(" " * begin_spaces + line for line in formatted_json.splitlines())
            print(indented_json_str)
    except TypeError as e:
        print(f"Error formatting JSON: {e}")

def read_yaml(filepath):
    try:
        with open(filepath, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.info(f"Error reading YAML file {filepath}: {e}")

def read_json(filepath):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.info(f"Error reading JSON file {filepath}: {e}")
 
def merge_dicts(params, in_place=True):
    """
    Merges two dictionaries with optional handling for lists and unique values.
    
    Args:
        params (dict): A dictionary containing:
            - 'dict1': First dictionary to merge.
            - 'dict2': Second dictionary to merge.
            - 'append_lists' (bool): If True, lists in dict1 and dict2 will be merged.
            - 'append_unique' (bool): If True, lists will only contain unique values after merging.
    
    Returns:
        dict: A new dictionary resulting from the merge.
    """
    dict1 = params.get('dict1', {})
    dict2 = params.get('dict2', {})
    if dict1 == dict2:
        return {'return': 0, 'merged': dict1, 'dict1': dict1}

    append_lists = params.get('append_lists', False)
    append_unique = params.get('append_unique', False)

    # Initialize the resulting merged dictionary
    if in_place:
        merged_dict = dict1
    else:
        merged_dict = dict1.copy()

    # Iterate over dict2 and merge it with dict1
    for key, value in dict2.items():
        if key in merged_dict:
            existing_value = merged_dict[key]

            if isinstance(existing_value, dict) and isinstance(value, dict):
                ii = {"dict1": existing_value, "dict2": value}
                for k in params:
                    if k not in ["dict1", "dict2"]:
                        ii[k] = params[k]
                merge_dicts(ii, in_place) 
            elif isinstance(existing_value, list) and isinstance(value, list):
                if append_lists:
                    if append_unique:
                        # Combine dictionaries uniquely based on their key-value pairs
                        seen = set()
                        merged_list = []
                        for item in existing_value + value:
                            if isinstance(item, dict):
                                try:
                                    item_frozenset = frozenset(item.items())
                                except TypeError:
                                    item_frozenset = id(item)
                            else:
                                item_frozenset = item
                            if item_frozenset not in seen:
                                seen.add(item_frozenset)
                                merged_list.append(item)
                        merged_dict[key] = merged_list
                    
                    else:
                        # Simply append the values
                        merged_dict[key] = existing_value + value
                else:
                    # If lists shouldn't be appended, override the value
                    merged_dict[key] = value
            else:
                # If it's not a list, simply overwrite or merge the value as needed
                merged_dict[key] = value
        else:
            # If key doesn't exist in dict1, add it directly
            merged_dict[key] = value


    return {'return': 0, 'merged': merged_dict, 'dict1': merged_dict}


def save_json(file_name, meta):
    """
    Saves the provided meta data to a JSON file.

    Args:
        file_name (str): The name of the file where the JSON data will be saved.
        meta (dict): The dictionary containing the data to be saved in JSON format.

    Returns:
        dict: A dictionary indicating success or failure of the operation.
            - 'return' (int): 0 if the operation was successful, > 0 if an error occurred.
            - 'error' (str): Error message, if any error occurred.
    """
    try:
        with open(file_name, 'w') as f:
            json.dump(meta, f, indent=4)
        return {'return': 0, 'error': ''}
    except Exception as e:
        return {'return': 1, 'error': str(e)}


def save_yaml(file_name, meta, sort_keys=True):
    """
    Saves the provided meta data to a YAML file.

    Args:
        file_name (str): The name of the file where the YAML data will be saved.
        meta (dict): The dictionary containing the data to be saved in YAML format.

    Returns:
        dict: A dictionary indicating success or failure of the operation.
            - 'return' (int): 0 if the operation was successful, > 0 if an error occurred.
            - 'error' (str): Error message, if any error occurred.
    """
    try:
        with open(file_name, 'w') as f:
            yaml.dump(meta, f, default_flow_style=False, sort_keys=sort_keys)
        return {'return': 0, 'error': ''}
    except Exception as e:
        return {'return': 1, 'error': str(e)}

def save_txt(file_name, string):
    """
    Saves the provided string to a text file.

    Args:
        file_name (str): The name of the file where the string data will be saved.
        string (str): The string content to be saved in the text file.

    Returns:
        dict: A dictionary indicating success or failure of the operation.
            - 'return' (int): 0 if the operation was successful, > 0 if an error occurred.
            - 'error' (str): Error message, if any error occurred.
    """
    try:
        with open(file_name, 'w') as f:
            f.write(string)
        return {'return': 0, 'error': ''}
    except Exception as e:
        return {'return': 1, 'error': str(e)}


def convert_args_to_dictionary(inp):
    args_dict = {}
    for key in inp:
        if "=" in key:
            split = key.split("=", 1)  # Split only on the first "="
            arg_key = split[0].strip("-")
            arg_value = split[1]

            # Handle lists: Only if "," is immediately before the "="
            if "," in arg_key:
                list_key, list_values = arg_key.rsplit(",", 1)
                if not list_values:  # Ensure "=" follows the last comma
                    args_dict[list_key] = arg_value.split(",")
                    continue

            # Handle dictionaries: `--adr.compiler.tags=gcc` becomes `{"adr": {"compiler": {"tags": "gcc"}}}`
            elif "." in arg_key:
                keys = arg_key.split(".")
                current = args_dict
                for part in keys[:-1]:
                    if part not in current or not isinstance(current[part], dict):
                        current[part] = {}
                    current = current[part]
                current[keys[-1]] = arg_value

            # Handle simple key-value pairs
            else:
                args_dict[arg_key] = arg_value

        # Handle flags: `--flag` becomes `{"flag": True}`
        elif key.startswith("--"):
            args_dict[key.strip("-")] = True

        # Handle short options (-j or -xyz)
        elif key.startswith("-"):
            for char in key.lstrip('-'):
                args_dict[char] = True

    return {'return': 0, 'args_dict': args_dict}

def is_uid(name):
        """
        Checks if the given name is a 16-digit hexadecimal UID.

        Args:
            name (str): The string to check.

        Returns:
            bool: True if the name is a 16-digit hexadecimal UID, False otherwise.
        """
        # Define a regex pattern for a 16-digit hexadecimal UID
        hex_uid_pattern = r"^[0-9a-fA-F]{16}$"

        # Check if the name matches the pattern
        return bool(re.fullmatch(hex_uid_pattern, name))


def is_valid_url(url):
    pattern = re.compile(
        r"^(https?|ftp)://"  # Protocol (http, https, ftp)
        r"(\S+:\S+@)?"  # Optional username:password@
        r"([a-zA-Z0-9.-]+)"  # Domain
        r"(:\d{2,5})?"  # Optional port
        r"(/[\S]*)?$",  # Path
        re.IGNORECASE
    )
    return re.match(pattern, url) is not None


def sub_input(i, keys, reverse=False):
    """
    Extracts and returns values from the dictionary based on the provided keys.

    Args:
        i (dict): The dictionary to extract values from.
        keys (list): A list of keys whose values are to be extracted from the dictionary.
        reverse (bool, optional): If True, the order of the keys in the result will be reversed. Default is False.

    Returns:
        dict: A dictionary with the extracted keys and their corresponding values.
    """
    if not isinstance(i, dict):
        return {'return': 1, 'error': 'Input is not a dictionary.'}

    if not isinstance(keys, list):
        return {'return': 1, 'error': 'Keys must be a list.'}

    # Filter dictionary using the provided keys
    result = {key: i.get(key) for key in keys if key in i}

    # If reverse is True, reverse the order of the result
    if reverse:
        result = dict(reversed(list(result.items())))

    return {'return': 0, 'result': result}

def assemble_object(alias, uid):
    """
    Assemble an object by concatenating the alias and uid.

    If either alias or uid is an empty string, it will not be included in the final result.

    Args:
        alias (str): The alias to be included in the concatenated string.
        uid (str): The uid to be included in the concatenated string.

    Returns:
        str: Concatenated result of alias and uid.
    """
    # Ensure both alias and uid are strings, default to empty string if None
    alias = alias or ''
    uid = uid or ''

    # Concatenate alias and uid with a separator if both are non-empty
    result = alias + (', ' if alias and uid else '') + uid

    return result

import importlib.util
import sys
import os


def load_python_module(params):
    """
    Load a Python module dynamically from a specified path and name.

    Args:
        params (dict): Dictionary containing:
            - 'path' (str): The directory path where the module is located.
            - 'name' (str): The name of the module to load (without the .py extension).

    Returns:
        dict: A dictionary containing either:
            - 'return' (int): 0 on success, 1 on error.
            - 'error' (str): Error message if return > 0.
            - 'code' (str): Loaded module code on success.
            - 'path' (str): Full path of the loaded module file.
    """
    module_name = params.get('name')
    module_path = params.get('path')

    # Ensure path and module name are provided
    if not module_name or not module_path:
        return {'return': 1, 'error': "Both 'path' and 'name' are required."}

    # Construct the full file path to the module
    full_path = os.path.join(module_path, module_name + '.py')

    # Check if the file exists at the given path
    if not os.path.isfile(full_path):
        return {'return': 1, 'error': f"Error: The file at '{full_path}' does not exist."}

    # Load the module dynamically using importlib
    try:
        # Specify the module spec
        spec = importlib.util.spec_from_file_location(module_name, full_path)
        if spec is None:
            return {'return': 1, 'error': f"Error: Could not load the module '{module_name}' from '{full_path}'."}

        # Load the module
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Add the module to sys.modules so it can be accessed like a normal module
        sys.modules[module_name] = module

        # Return success with loaded code and full path
        return {'return': 0, 'code': module, 'path': full_path}

    except Exception as e:
        return {'return': 1, 'error': f"Error: Failed to load module '{module_name}' from '{full_path}'. Error: {str(e)}"}

def convert_env_to_dict(env_text):
    """
    Convert a multiline string where each line is in the format 'key=value' into a dictionary.

    Args:
        env_text (str): A multiline string with lines in the form 'key=value'.

    Returns:
        dict: A dictionary where keys are the left part of 'key=value' and values are the right part.
    """
    env_dict = {}

    # Split the text into lines and process each line
    for line in env_text.splitlines():
        # Strip any leading/trailing whitespace and ensure the line is not empty
        line = line.strip()
        if line and '=' in line:
            key, value = line.split('=', 1)
            env_dict[key.strip()] = value.strip()

    return {'return': 0, 'dict': env_dict}

def load_json(file_name, encoding = None):
    """
    Load JSON data from a file and handle errors.

    Args:
        file_name (str): The path to the JSON file to load.

    Returns:
        dict: A dictionary containing the result of the operation:
            - 'return': 0 on success, > 0 on error
            - 'error': Error message if 'return' > 0
            - 'meta': The loaded JSON data if successful
    """
    try:
        if encoding:
            with open(file_name, 'r', encoding=encoding) as f:
                meta = json.load(f)
        else:
            with open(file_name, 'r') as f:
                meta = json.load(f)

        return {'return': 0, 'meta': meta}

    except FileNotFoundError:
        return {'return': 1, 'error': f"File '{file_name}' not found."}

    except json.JSONDecodeError:
        return {'return': 1, 'error': f"Error decoding JSON in file '{file_name}'."}

    except Exception as e:
        return {'return': 1, 'error': f"An unexpected error occurred: {str(e)}"}



def get_new_uid():
    """
    Generate a new unique identifier (UID).

    Returns:
        dict: A dictionary containing:
            - return (int): 0 if successful, >0 if there was an error.
            - uid (str): The newly generated unique identifier.
    """
    try:
        new_uid = str(uuid.uuid4().hex[:16])
        return {"return": 0, "uid": new_uid}
    except Exception as e:
        return {"return": 1, "error": f"Failed to generate UID: {str(e)}"}
    
def modify_git_url(get_type, url, params={}):
    """
    Modify the GitHub url to support cloning of repo with either ssh or pat

    Returns:
        dict: A dictionary containing:
            - return (int): 0 if successful, >0 if there was an error.
            - url (str): Modified git url.
    """
    from giturlparse import parse
    p = parse(url)
    if get_type == "ssh":
        return {"return": 0, "url": p.url2ssh }
    elif get_type == "pat":
        token = params['token']
        return {"return": 0, "url":"https://git:" + token + "@" + p.host + "/" + p.owner + "/" + p.repo }
    else:
        return {"return": 1, "error": f"Unsupported type: {get_type}"}

def convert_tags_to_list(tags_string):
    """
    Convert a comma-separated string into a list of tags.

    Args:
        tags_string (str): Comma-separated string of tags.

    Returns:
        list: A list of trimmed tags. Empty strings are excluded.
    """
    if not isinstance(tags_string, str):
        return {'return': 1, 'error': 'Input must be a string.'}

    tags_list = [tag.strip() for tag in tags_string.split(',') if tag.strip()]

    return {'return': 0, 'tags': tags_list}



def extract_file(options):
    """
    Extracts a compressed file, optionally stripping folder levels.

    Args:
        options (dict): A dictionary with the following keys:
            - 'filename' (str): The path to the compressed file to extract.
            - 'strip_folders' (int, optional): The number of folder levels to strip. Default is 0.

    Raises:
        ValueError: If the file format is unsupported.
        FileNotFoundError: If the specified file does not exist.
    """
    filename = options.get('filename')
    strip_folders = options.get('strip_folders', 0)

    if not filename or not os.path.exists(filename):
        raise FileNotFoundError(f"File not found: {filename}")

    extract_to = os.path.join(os.path.dirname(filename), "extracted")
    os.makedirs(extract_to, exist_ok=True)

    # Check file type and extract accordingly
    if zipfile.is_zipfile(filename):
        with zipfile.ZipFile(filename, 'r') as archive:
            members = archive.namelist()
            for member in members:
                # Strip folder levels
                stripped_path = os.path.join(
                    extract_to, *member.split(os.sep)[strip_folders:]
                )
                if member.endswith('/'):  # Directory
                    os.makedirs(stripped_path, exist_ok=True)
                else:  # File
                    os.makedirs(os.path.dirname(stripped_path), exist_ok=True)
                    with archive.open(member) as source, open(stripped_path, 'wb') as target:
                        shutil.copyfileobj(source, target)

    elif tarfile.is_tarfile(filename):
        with tarfile.open(filename, 'r') as archive:
            members = archive.getmembers()
            for member in members:
                if strip_folders:
                    parts = member.name.split('/')
                    member.name = '/'.join(parts[strip_folders:])
                archive.extract(member, path=extract_to)

    else:
        raise ValueError(f"Unsupported file format: {filename}")

    print(f"Extraction complete. Files extracted to: {extract_to}")

