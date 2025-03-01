
import logging
import os  
import subprocess  
import mlc   
import pytest

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log message format
    handlers=[
        logging.FileHandler("test_mlc_access.log"),  # Log to a file
        logging.StreamHandler()  # Log to the console
    ]
)

logger = logging.getLogger(__name__)

# Helper function to process and log output
def process_output(target, action, res):
    """Helper function to process and log the output of mlc.access."""
    if action in ["find"]:
        if "list" not in res:
            logger.error("'list' entry not found in find result")
            raise Exception("'list' entry not found in find result")
        if len(res['list']) == 0:
            logger.warning("No entry found for the particular action and target!")
        else:
            for item in res['list']:
                logger.info(f"Item path: {item.path}")
                if action == "show":
                    logger.info(f"{target} meta:")
                    logger.info(item.meta)

# Test: Find repo
def test_find_repo():
    """Test the 'find repo' functionality of mlc.access."""
    logger.info("###### TEST - find repo")

    # Test with <repo_owner>@<repos_name>
    res = mlc.access({
        "target": "repo",
        "action": "find",
        "repo": "anandhu-eng@mlperf-automations"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    process_output("repo", "find", res)

    # Test with <repo_url>
    res = mlc.access({
        "target": "repo",
        "action": "find",
        "repo": "https://github.com/mlcommons/mlperf-automations.git"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    process_output("repo", "find", res)

    # Test with <repo_uid>
    res = mlc.access({
        "target": "repo",
        "action": "find",
        "repo": "9cf241afa6074c89"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    process_output("repo", "find", res)

    # Test with <repo_alias>
    res = mlc.access({
        "target": "repo",
        "action": "find",
        "repo": "mlcommons@mlperf-automations"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    process_output("repo", "find", res)

    # Test with <repo_alias>,<repo_uid>
    res = mlc.access({
        "target": "repo",
        "action": "find",
        "repo": "mlcommons@mlperf-automations,9cf241afa6074c89"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    process_output("repo", "find", res)

    logger.info("###### TEST find repo SUCCESSFUL.")

# Test: List repo
def test_list_repo():
    """Test the 'list repo' functionality of mlc.access."""
    logger.info("###### TEST - list repo")
    res = mlc.access({
        "target": "repo",
        "action": "list"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    logger.info("###### TEST list repo SUCCESSFUL.")

# Test: Find cache
def test_find_cache():
    """Test the 'find cache' functionality of mlc.access."""
    logger.info("###### TEST - find cache")
    res = mlc.access({
        "target": "cache",
        "action": "find",
        "tags": "get,imagenet-aux"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    process_output("cache", "find", res)
    logger.info("###### TEST find cache SUCCESSFUL.")

# Test: Show cache
def test_show_cache():
    """Test the 'show cache' functionality of mlc.access."""
    logger.info("###### TEST - show cache")
    res = mlc.access({
        "target": "cache",
        "action": "show",
        "tags": "get,imagenet-aux"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    process_output("cache", "show", res)
    logger.info("###### TEST show cache SUCCESSFUL.")

# Test: Remove cache
def test_rm_cache():
    """Test the 'rm cache' functionality of mlc.access."""
    logger.info("###### TEST - rm cache")
    res = mlc.access({
        "target": "cache",
        "action": "rm",
        "tags": "get,imagenet-aux",
        "f": True
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    logger.info("###### TEST rm cache SUCCESSFUL.")

# Test: Copy script
def test_cp_script():
    """Test the 'cp script' functionality of mlc.access."""
    logger.info("###### TEST - cp script")
    res = mlc.access({
        "target": "script",
        "action": "cp",
        "src": "detect-os",
        "dest": "my-os-detect"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    logger.info("###### TEST cp script SUCCESSFUL.")

# Test: Add repo
def test_add_repo():
    """Test the 'add repo' functionality of mlc.access."""
    logger.info("###### TEST - add repo")
    res = mlc.access({
        "target": "repo",
        "action": "add",
        "repo": "my-new-repo"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    logger.info("Successfully added repo")
    logger.info("###### TEST add repo SUCCESSFUL.")

# Test: Add script
def test_add_script():
    """Test the 'add script' functionality of mlc.access."""
    logger.info("###### TEST - add script")
    res = mlc.access({
        "target": "script",
        "action": "add",
        "item": "my-script-1",
        "tags": "my,new-tags-1"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    logger.info("script with alias my-script-1 successfully added")
    logger.info("###### TEST add script SUCCESSFUL.")

# Test: Move script
def test_mv_script():
    """Test the 'mv script' functionality of mlc.access."""
    logger.info("###### TEST - mv script")
    res = mlc.access({
        "target": "script",
        "action": "mv",
        "src": "my-script-1",
        "dest": "moved-my-script-1"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    logger.info("###### TEST mv script SUCCESSFUL.")

# Test: Show script
def test_show_script():
    """Test the 'show script' functionality of mlc.access."""
    logger.info("###### TEST - show script")
    res = mlc.access({
        "target": "script",
        "action": "show",
        "tags": "run-mlperf,inference"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    process_output("script", "show", res)
    logger.info("###### TEST show script SUCCESSFUL.")

# Test: Find script
def test_find_script():
    """Test the 'find script' functionality of mlc.access."""
    logger.info("###### TEST - find script")
    res = mlc.access({
        "target": "script",
        "action": "find",
        "tags": "run-mlperf,inference"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    process_output("script", "find", res)
    logger.info("###### TEST find script SUCCESSFUL.")

# Test: Remove script
def test_rm_script():
    """Test the 'rm script' functionality of mlc.access."""
    logger.info("###### TEST - rm script")
    res = mlc.access({
        "target": "script",
        "action": "rm",
        "tags": "app,image,corner-detection",
        "f": True
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    logger.info("###### TEST rm script SUCCESSFUL.")

# Test: List script
def test_list_script():
    """Test the 'list script' functionality of mlc.access."""
    logger.info("###### TEST - list script")
    res = mlc.access({
        "target": "script",
        "action": "list"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    logger.info("###### TEST list script SUCCESSFUL.")

# Test: List cache
def test_list_cache():
    """Test the 'list cache' functionality of mlc.access."""
    logger.info("###### TEST - list cache")
    res = mlc.access({
        "target": "cache",
        "action": "list"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    logger.info("###### TEST list cache SUCCESSFUL.")

# Test: Run script
def test_run_script():
    """Test the 'run script' functionality of mlc.access."""
    logger.info("###### TEST - run script")
    res = mlc.access({
        "target": "script",
        "action": "run",
        "tags": "get,imagenet-aux"
    })
    assert res['return'] == 0, f"Test failed: {res['error']}"
    logger.info("###### TEST run script SUCCESSFUL.")