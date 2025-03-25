# **Script Action**  

The following actions are supported for managing scripts in **MLCFlow**.  

---

## **Syntax Variations**  

MLC scripts can be identified in different ways:  

1. **Using tags:** `--tags=<comma-separated-tags>` (e.g., `--tags=detect,os`)  
2. **Using alias:** `<script_alias>` (e.g., `detect-os`)  
3. **Using UID:** `<script_uid>` (e.g., `5b4e0237da074764`)  
4. **Using both alias and UID:** `<script_alias>,<script_uid>` (e.g., `detect-os,5b4e0237da074764`)  

!!! note  
    For simplicity, syntax variations are only shown for the `find` action, but similar options apply to all other actions.  

---

## **Find(Alias: Search)**  

The `find/search` action retrieves the path of scripts available in MLC repositories.  

### **Syntax Variations**  

| Command Format | Example Usage |
|---------------|--------------|
| `mlc find script --tags=<tags>` | `mlc find script --tags=detect,os` |
| `mlc find script <script_alias>` | `mlc find script detect-os` |
| `mlc find script <script_uid>` | `mlc find script 5b4e0237da074764` |
| `mlc find script <script_alias>,<script_uid>` | `mlc find script detect-os,5b4e0237da074764` |

<details>
  <summary><strong>Example Output</strong> 📌</summary>

  ```bash
  arjun@intel-spr-i9:~$ mlc find script --tags=detect,os -j
  [2025-02-14 02:55:12,999 main.py:1686 INFO] - Item path: /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/detect-os
  ```
</details>  

🔹 **Example usage:** [GitHub Workflow](https://github.com/mlcommons/mlcflow/blob/d0269b47021d709e0ffa7fe0db8c79635bfd9dff/.github/workflows/test-mlc-core-actions.yaml)  

---

## **Show**  

Retrieves the path and metadata of scripts in MLC repositories.  

**Example Command:**  
```bash
mlc show script --tags=detect,os
```

<details>
  <summary><strong>Example Output</strong> 📌</summary>

  ```bash
  arjun@intel-spr-i9:~$ mlc show script --tags=detect,os
  [2025-02-14 02:56:16,604 main.py:1404 INFO] - Showing script with tags: detect,os
  Location: /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/detect-os:
  Main Script Meta:
      uid: 863735b7db8c44fc
      alias: detect-os
      tags: ['detect-os', 'detect', 'os', 'info']
      new_env_keys: ['MLC_HOST_OS_*', '+MLC_HOST_OS_*', 'MLC_HOST_PLATFORM_*', 'MLC_HOST_PYTHON_*', 'MLC_HOST_SYSTEM_NAME', 'MLC_RUN_STATE_DOCKER', '+PATH']
      new_state_keys: ['os_uname_*']
  ......................................................
  For full script meta, see meta file at /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/detect-os/meta.yaml
  ```
</details>  

---

## **Add**  

Creates a new script in a registered MLC repository.  

**Example Command:**  
```bash
mlc add script <user@repo>:new_script --tags=benchmark
```

**Options:**  
- `--template_tags`: A comma-separated list of tags to create a new MLC script based on existing templates.  

<details>
  <summary><strong>Example Output</strong> 📌</summary>

  ```bash
  arjun@intel-spr-i9:~$ mlc add script gateoverflow@mlperf-automations --tags=benchmark --template_tags=app,mlperf,inference
  More than one script found for None:
  1. /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/app-mlperf-inference-mlcommons-python
  2. /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/app-mlperf-inference-ctuning-cpp-tflite
  3. /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/app-mlperf-inference
  4. /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/app-mlperf-inference-mlcommons-cpp
  Select the correct one (enter number, default=1): 1
  [2025-02-14 02:58:33,453 main.py:664 INFO] - Folder successfully copied from /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/app-mlperf-inference-mlcommons-python to /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/gateoverflow@mlperf-automations
  ```
</details>  

---

## **Move (`mv`)**  

Transfers a script between repositories or renames a script within the same repository.  

**Example Command:**  
```bash
mlc mv script <user@source_repo>:script <user@target_repo>:script
```

---

## **Copy (`cp`)**  

Duplicates a script between repositories or within the same repository.  

**Example Command:**  
```bash
mlc cp script <user@source_repo>:script <user@target_repo>:script
```

---

## **Remove (`rm`)**  

Deletes one or more scripts from MLC repositories.  

**Example Command:**  
```bash
mlc rm script --tags=detect,os -f
```

---

## **List**  

Lists all the scripts and their paths present in repos which are registered in MLC.

**Example Command:**  
```bash
mlc list script
```

---

## **Run**  

Executes a script from an MLC repository.  

**Example Command:**  
```bash
mlc run script --tags=detect,os -j
```

**Options:**  

- `-j`: Shows the output in a JSON format

- `mlcr` can be used as a shortcut to `mlc run script --tags=`

- `--input`:

- `--path`:

- `--outdirname`:

- `--new`:

- `--force_cache`:

- `--version`:

- `--version_max`:

- `--version_min`:

- `--quiet`:

- *`<Individual script inputs>`: In addition to the above options an `mlcr` command also takes any input specified with in a script meta in `input_mappings` as its input.

**Log Levels**

- *Default*  : Provides all logs at the `info` level.

- *Silent* `[--silent/-s]`  : Disables all `debug` and `info` level logs from automation. Logs from individual scripts will still be visible.

- *verbose* `[--verbose/-v]` : Displays both `info` and `debug` level logs from automation, along with logs from individual scripts.

<details>
  <summary><strong>Example Output</strong> 📌</summary>
```
arjun@arjun-spr:~$ mlcr detect,os -j
[2025-02-16 03:30:40,702 module.py:560 INFO] - * mlcr detect,os
[2025-02-16 03:30:40,704 module.py:5334 INFO] -        ! cd /home/arjun
[2025-02-16 03:30:40,704 module.py:5335 INFO] -        ! call /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/detect-os/run.sh from tmp-run.sh
[2025-02-16 03:30:40,740 module.py:5481 INFO] -        ! call "postprocess" from /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/detect-os/customize.py
[2025-02-16 03:30:40,749 module.py:2181 INFO] - {
  "return": 0,
  "env": {
    "MLC_HOST_OS_TYPE": "linux",
    "MLC_HOST_OS_BITS": "64",
    "MLC_HOST_OS_FLAVOR": "ubuntu",
    "MLC_HOST_OS_FLAVOR_LIKE": "debian",
    "MLC_HOST_OS_VERSION": "24.04",
    "MLC_HOST_OS_KERNEL_VERSION": "6.8.0-52-generic",
    "MLC_HOST_OS_GLIBC_VERSION": "2.39",
    "MLC_HOST_OS_MACHINE": "x86_64",
    "MLC_HOST_OS_PACKAGE_MANAGER": "apt",
    "MLC_HOST_OS_PACKAGE_MANAGER_INSTALL_CMD": "DEBIAN_FRONTEND=noninteractive apt-get install -y",
    "MLC_HOST_OS_PACKAGE_MANAGER_UPDATE_CMD": "apt-get update -y",
    "+MLC_HOST_OS_DEFAULT_LIBRARY_PATH": [
      "/usr/local/lib/x86_64-linux-gnu",
      "/lib/x86_64-linux-gnu",
      "/usr/lib/x86_64-linux-gnu",
      "/usr/lib/x86_64-linux-gnu64",
      "/usr/local/lib64",
      "/lib64",
      "/usr/lib64",
      "/usr/local/lib",
      "/lib",
      "/usr/lib",
      "/usr/x86_64-linux-gnu/lib64",
      "/usr/x86_64-linux-gnu/lib"
    ],
    "MLC_HOST_PLATFORM_FLAVOR": "x86_64",
    "MLC_HOST_PYTHON_BITS": "64",
    "MLC_HOST_SYSTEM_NAME": "arjun-spr"
  },
  "new_env": {
    "MLC_HOST_OS_TYPE": "linux",
    "MLC_HOST_OS_BITS": "64",
    "MLC_HOST_OS_FLAVOR": "ubuntu",
    "MLC_HOST_OS_FLAVOR_LIKE": "debian",
    "MLC_HOST_OS_VERSION": "24.04",
    "MLC_HOST_OS_KERNEL_VERSION": "6.8.0-52-generic",
    "MLC_HOST_OS_GLIBC_VERSION": "2.39",
    "MLC_HOST_OS_MACHINE": "x86_64",
    "MLC_HOST_OS_PACKAGE_MANAGER": "apt",
    "MLC_HOST_OS_PACKAGE_MANAGER_INSTALL_CMD": "DEBIAN_FRONTEND=noninteractive apt-get install -y",
    "MLC_HOST_OS_PACKAGE_MANAGER_UPDATE_CMD": "apt-get update -y",
    "+MLC_HOST_OS_DEFAULT_LIBRARY_PATH": [
      "/usr/local/lib/x86_64-linux-gnu",
      "/lib/x86_64-linux-gnu",
      "/usr/lib/x86_64-linux-gnu",
      "/usr/lib/x86_64-linux-gnu64",
      "/usr/local/lib64",
      "/lib64",
      "/usr/lib64",
      "/usr/local/lib",
      "/lib",
      "/usr/lib",
      "/usr/x86_64-linux-gnu/lib64",
      "/usr/x86_64-linux-gnu/lib"
    ],
    "MLC_HOST_PLATFORM_FLAVOR": "x86_64",
    "MLC_HOST_PYTHON_BITS": "64",
    "MLC_HOST_SYSTEM_NAME": "arjun-spr"
  },
  "state": {
    "os_uname_machine": "x86_64",
    "os_uname_all": "Linux arjun-spr 6.8.0-52-generic #53-Ubuntu SMP PREEMPT_DYNAMIC Sat Jan 11 00:06:25 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux"
  },
  "new_state": {
    "os_uname_machine": "x86_64",
    "os_uname_all": "Linux arjun-spr 6.8.0-52-generic #53-Ubuntu SMP PREEMPT_DYNAMIC Sat Jan 11 00:06:25 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux"
  },
  "deps": []
}
```

</details>
---

## **Docker Execution**  

Runs scripts inside a **containerized environment**.  

📌 Please refer to the [Docker README](#) for the full list of Docker options for MLC scripts.  

**Example Command:**  
```bash
mlc docker script --tags=detect,os -j
```

---

## **Test**  

Validates scripts configured with a `tests` section in `meta.yaml`.  

**Example Command:**  
```bash
mlc test script --tags=benchmark
```

🔹 **Example of test configuration:** [Meta.yaml Example](https://github.com/mlcommons/mlperf-automations/blob/0e647d7126e610d010a21dbfccca097febe80af9/script/get-generic-sys-util/meta.yaml#L24)  

---
