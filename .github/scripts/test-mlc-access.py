import os
import subprocess
import mlc


###### TEST 1 - pull repo - Pull a forked MLOps repository
print("###### TEST 1 - pull repo - Pull a forked MLOps repository")
# Define paths
GH_MLC_REPO_PATH_FORK = os.path.join(os.path.expanduser("~"), "MLC", "repos", "anandhu-eng@mlperf-automations")
GH_MLC_REPO_JSON_PATH = os.path.join(os.path.expanduser("~"), "MLC", "repos", "repos.json")

res = mlc.access({
    "automation": "repo",
    "action": "pull",
    "repo": "anandhu-eng@mlperf-automations",
    "checkout": "dev"
})
if res['return'] > 0:
    raise Exception(f"{res['error']}")

# Check if the repository folder exists
if not os.path.isdir(GH_MLC_REPO_PATH_FORK):
    raise Exception(f"Repository folder {GH_MLC_REPO_PATH_FORK} not found. Exiting with failure.")
    
# Check if the JSON file exists
if not os.path.isfile(GH_MLC_REPO_JSON_PATH):
    raise Exception(f"File {GH_MLC_REPO_JSON_PATH} does not exist. Exiting with failure.")

# Check if the repository path is in the JSON file
with open(GH_MLC_REPO_JSON_PATH, 'r') as json_file:
    if GH_MLC_REPO_PATH_FORK not in json_file.read():
        raise Exception(f"Path {GH_MLC_REPO_PATH_FORK} not found in {GH_MLC_REPO_JSON_PATH}. Exiting with failure.")

# Check the current branch
try:
    CURRENT_BRANCH = subprocess.check_output(
        ["git", "-C", GH_MLC_REPO_PATH_FORK, "rev-parse", "--abbrev-ref", "HEAD"],
        text=True
    ).strip()
except subprocess.CalledProcessError:
    raise Exception(f"Failed to get the current branch for {GH_MLC_REPO_PATH_FORK}. Exiting with failure.")

if CURRENT_BRANCH != "dev":
    raise Exception(f"Expected branch 'dev', but found '{CURRENT_BRANCH}'. Exiting with failure.")

print("###### TEST 1 SUCCESSFULL.")

###### TEST 2 - find repo

print("###### TEST 2 - find repo")
# format: <repo_owner>@<repos_name>
res = mlc.access({
    "automation": "repo",
    "action": "find",
    "repo": "anandhu-eng@mlperf-automations"
})
if res['return'] > 0:
    raise Exception(f"{res['error']}")

# format: <repo_url>
res = mlc.access({
    "automation": "repo",
    "action": "find",
    "repo": "https://github.com/mlcommons/mlperf-automations.git"
})
if res['return'] > 0:
    raise Exception(f"{res['error']}")

# format: <repo_uid>
res = mlc.access({
    "automation": "repo",
    "action": "find",
    "repo": "9cf241afa6074c89"
})
if res['return'] > 0:
    raise Exception(f"{res['error']}")

# format: <repo_alias>
res = mlc.access({
    "automation": "repo",
    "action": "find",
    "repo": "mlcommons@mlperf-automations"
})
if res['return'] > 0:
    raise Exception(f"{res['error']}")

# format: <repo_alias>,<repo_uid>
res = mlc.access({
    "automation": "repo",
    "action": "find",
    "repo": "mlcommons@mlperf-automations,9cf241afa6074c89"
})
print(res)
if res['return'] > 0:
    raise Exception(f"{res['error']}")

print("###### TEST 2 SUCCESSFUL.")

###### TEST 3 - pull repo - Test conflicting repo scenario

print("###### TEST 3 - pull repo - Test conflicting repo scenario")
# Define paths
GH_MLC_REPO_PATH = os.path.join(os.path.expanduser("~"), "MLC", "repos", "mlcommons@mlperf-automations")
GH_MLC_REPO_JSON_PATH = os.path.join(os.path.expanduser("~"), "MLC", "repos", "repos.json")

# Pull the MLOps repository
res = mlc.access({
    "automation": "repo",
    "action": "pull",
    "repo": "mlcommons@mlperf-automations",
    "checkout": "dev"
})
if res['return'] > 0:
    raise Exception(f"{res['error']}")

# Check if the repository folder exists
if not os.path.isdir(GH_MLC_REPO_PATH):
    raise Exception(f"Repository folder {GH_MLC_REPO_PATH} not found. Exiting with failure.")

# Check if the JSON file exists
if not os.path.isfile(GH_MLC_REPO_JSON_PATH):
    raise Exception(f"File {GH_MLC_REPO_JSON_PATH} does not exist. Exiting with failure.")

# Check if the repository path is in the JSON file
with open(GH_MLC_REPO_JSON_PATH, 'r') as json_file:
    if GH_MLC_REPO_PATH not in json_file.read():
        raise Exception(f"Path {GH_MLC_REPO_PATH} not found in {GH_MLC_REPO_JSON_PATH}. Exiting with failure.")

# Check for the conflicting path
GH_MLC_REPO_PATH_FORK = os.path.join(os.path.expanduser("~"), "MLC", "repos", "anandhu-eng@mlperf-automations")
with open(GH_MLC_REPO_JSON_PATH, 'r') as json_file:
    if GH_MLC_REPO_PATH_FORK in json_file.read():
        raise Exception(f"Path {GH_MLC_REPO_PATH_FORK} also found in {GH_MLC_REPO_JSON_PATH}. This should have been replaced. Exiting with failure.")

# Check the current branch
try:
    CURRENT_BRANCH = subprocess.check_output(
        ["git", "-C", GH_MLC_REPO_PATH, "rev-parse", "--abbrev-ref", "HEAD"],
        text=True
    ).strip()
except subprocess.CalledProcessError:
    raise Exception(f"Failed to get the current branch for {GH_MLC_REPO_PATH}. Exiting with failure.")

if CURRENT_BRANCH != "dev":
    raise Exception(f"Expected branch 'dev', but found '{CURRENT_BRANCH}'. Exiting with failure.")

res = mlc.access({
    "automation": "repo",
    "action": "pull"
})
if res['return'] > 0:
    raise Exception(f"{res['error']}")

print("###### TEST 3 SUCCESSFUL.")