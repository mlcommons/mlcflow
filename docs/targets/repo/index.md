# Repo

Currently, the following actions are supported for repos:

## **Syntax Variations**  

In MLCFlow, repos can be identified in different ways:  

1. **Using MLC repo folder name format:** `<repoowner@reponame>` (e.g.,`mlcommons@mlperf-automations`)
2. **Using alias:** `<repo_alias>`  (e.g., `mlcommons@mlperf-automations`)  
3. **Using UID:** `<repo_uid>`  (e.g., `9cf241afa6074c89`)  
4. **Using both alias and UID:** `<repo_alias>,<repo_uid>` (e.g., `mlcommons@mlperf-automations,9cf241afa6074c89`)
5. **Using URL:** `<repo_url>` (e.g., `https://github.com/mlcommons/mlperf-automations`)  

!!! note  
    - `repo uid` and `repo alias` for a particular MLC repository can be found inside `meta.yml` file.
    - For simplicity, syntax variations are only shown for the `find` action, but similar options apply to all other actions.  

## Find

`find` action retrieves the path of a specific repository registered in MLCFlow.

### **Syntax Variations**  

| Command Format | Example Usage |
|---------------|--------------|
| `mlc find repo <repo_owner@repo_name>` | `mlc find repo mlcommons@mlperf-automations` |
| `mlc find repo <repo_alias>` | `mlc find repo mlcommons@mlperf-automations` |
| `mlc find repo <repo_uid>` | `mlc find repo 9cf241afa6074c89` |
| `mlc find script <repo_alias>,<repo_uid>` | `mlc find repo mlcommons@mlperf-automations,9cf241afa6074c89` |
| `mlc find repo <repo_url>` | `mlc find repo https://github.com/mlcommons/mlperf-automations` |

Examples of `find` action for `repo` target can be found inside the GitHub action workflow [here](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml).

<details>
  <summary><strong>Example Output</strong> 📌</summary>

  ```bash
  anandhu@anandhu-VivoBook-ASUSLaptop-X515UA-M515UA:~$ mlc find repo mlcommons@mlperf-automations
  [2025-02-19 15:32:18,352 main.py:1737 INFO] - Item path: /home/anandhu/MLC/repos/mlcommons@mlperf-automations
  ```
</details>  

## Add

`add` action is used to create a new MLC repo and register in MLCFlow. The newly created repo folder will be present inside the `repos` folder within the parent `MLC` directory.

**Example Command**

```bash
mlc add repo mlcommons@script-automations
```
<details>
  <summary><strong>Example Output</strong> 📌</summary>

  ```bash
    anandhu@anandhu-VivoBook-ASUSLaptop-X515UA-M515UA:~$ mlc add repo mlcommons@script-automations
    [2025-02-19 16:34:37,570 main.py:1085 INFO] - New repo path: /home/anandhu/MLC/repos/mlcommons@script-automations
    [2025-02-19 16:34:37,573 main.py:1126 INFO] - Added new repo path: /home/anandhu/MLC/repos/mlcommons@script-automations
    [2025-02-19 16:34:37,573 main.py:1130 INFO] - Updated repos.json at /home/anandhu/MLC/repos/repos.json
  ```
</details>  

Examples of `add` action for `repo` target could be found inside the GitHub action workflow [here](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml).

!!! note  
    - `repo_uid` is not supported in the `add` action for `repo` target since `uid` for the repo is assigned automatically while creating the repository. 

## Pull

`pull` action clones an MLC repository and registers it in MLC.

If the repository already exists locally in MLC repos directory, it fetches the latest changes if there are no uncommited modifications(does not include untracked files/folders). The `pull` action could be also used to checkout to a particular branch or release tag with flags `--checkout` and `--tag`.

**Example Command**

```bash
mlc pull repo mlcommons@mlperf-automations
```

<details>
  <summary><strong>Example Output</strong> 📌</summary>

  ```bash
    anandhu@anandhu-VivoBook-ASUSLaptop-X515UA-M515UA:~$ mlc pull repo mlcommons@mlperf-automations
    [2025-02-19 16:46:27,208 main.py:1260 INFO] - Cloning repository https://github.com/mlcommons/mlperf-automations.git to /home/anandhu/MLC/repos/mlcommons@mlperf-automations...
    Cloning into '/home/anandhu/MLC/repos/mlcommons@mlperf-automations'...
    remote: Enumerating objects: 77610, done.
    remote: Counting objects: 100% (2199/2199), done.
    remote: Compressing objects: 100% (1103/1103), done.
    remote: Total 77610 (delta 1616), reused 1109 (delta 1095), pack-reused 75411 (from 2)
    Receiving objects: 100% (77610/77610), 18.36 MiB | 672.00 KiB/s, done.
    Resolving deltas: 100% (53818/53818), done.
    [2025-02-19 16:46:57,604 main.py:1288 INFO] - Repository successfully pulled.
    [2025-02-19 16:46:57,605 main.py:1289 INFO] - Registering the repo in repos.json
    [2025-02-19 16:46:57,605 main.py:1126 INFO] - Added new repo path: /home/anandhu/MLC/repos/mlcommons@mlperf-automations
    [2025-02-19 16:46:57,606 main.py:1130 INFO] - Updated repos.json at /home/anandhu/MLC/repos/repos.json
  ```
</details>  


- The `--checkout` flag can be used if a user needs to check out a specific commit or branch after cloning. The user must provide the commit SHA if they want to check out a specific commit. This flag can be used in cases where the repository exists locally.
- The `--branch` flag can be used if a user needs to check out a specific branch after cloning. The user must provide the branch name. This flag will only work when cloning a new repository.
- The `--tag` flag can be used to check out a particular release tag.
- `--pat=<access_token>` or `--ssh` flag can be used to clone a private repository.

Examples of `pull` action for `repo` target could be found inside the GitHub action workflow [here](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml).

!!! note  
    - `repo_uid` and `repo_alias` are not supported in the `pull` action for the `repo` target.  
    - Only one of `--checkout`, `--branch`, or `--tag` should be specified when using this action.  

## List

`list` action displays all registered MLC repositories along with their aliases and paths.

**Example Command**

```bash
mlc list repo
```

<details>
  <summary><strong>Example Output</strong> 📌</summary>

  ```bash
    anandhu@anandhu-VivoBook-ASUSLaptop-X515UA-M515UA:~$ mlc list repo
    [2025-02-19 16:56:31,847 main.py:1349 INFO] - Listing all repositories.

    Repositories:
    -------------
    - Alias: local
    Path:  /home/anandhu/MLC/repos/local

    -  Alias: mlcommons@mlperf-automations
    Path:  /home/anandhu/MLC/repos/mlcommons@mlperf-automations

    -------------
    [2025-02-19 16:56:31,850 main.py:1356 INFO] - Repository listing ended

  ```
</details>  

Example of `list` action for `repo` target could be found inside the GitHub action workflow [here](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml).

## Rm (Remove)

`rm` action removes a specified repository from MLCFlow, deleting both the repo folder and its registration.

**Example Command**

```bash
mlc rm repo mlcommons@mlperf-automations
```

<details>
    <summary><strong>Example Output</strong></summary>

    ```bash
        anandhu@anandhu-VivoBook-ASUSLaptop-X515UA-M515UA:~$ mlc rm repo mlcommons@mlperf-automations
        [2025-02-19 17:01:59,483 main.py:1360 INFO] - rm command has been called for repo. This would delete the repo folder and unregister the repo from repos.json
        [2025-02-19 17:01:59,521 main.py:1380 INFO] - No local changes detected. Removing repo...
        [2025-02-19 17:01:59,581 main.py:1384 INFO] - Repo mlcommons@mlperf-automations residing in path /home/anandhu/MLC/repos/mlcommons@mlperf-automations has been successfully removed
        [2025-02-19 17:01:59,581 main.py:1385 INFO] - Checking whether the repo was registered in repos.json
        [2025-02-19 17:01:59,581 main.py:1134 INFO] - Unregistering the repo in path /home/anandhu/MLC/repos/mlcommons@mlperf-automations
        [2025-02-19 17:01:59,581 main.py:1144 INFO] - Path: /home/anandhu/MLC/repos/mlcommons@mlperf-automations has been removed.
    ```

An example of the `rm` action for the `repo` target can be found in the GitHub Actions workflow [here](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml).

