
## ** Native Script Execution & Automatic Script Selection**

In MLC script execution, the default native script filename is **`run`**, with the extension **`.sh`** on Unix platforms and **`.bat`** on Windows. Users can customize this by providing a different script name using the `script_name` parameter.  

Once the script name is specified, **MLC automatically selects the most suitable script variant** based on the **OS and platform** where it is being executed.

### **Behavior**  

The following explanation assumes the **`.sh`** extension for Unix-based systems, but the same logic applies to **`.bat`** files on Windows.

1. **Checks Available Scripts**:  
   - If no script in the directory starts with `"script_name-"`, the function **skips unnecessary checks** and returns the default `"script_name.sh"`.
   - If matching scripts exist, it proceeds to find the best match.

2. **Priority Order for Script Selection**:  
   The function checks for files in the following order:
   1. `{script_name}-{MLC_HOST_OS_FLAVOR}-{MLC_HOST_OS_VERSION}-{MLC_HOST_PLATFORM_FLAVOR}.sh`
   2. `{script_name}-{MLC_HOST_OS_FLAVOR}-{MLC_HOST_OS_VERSION}.sh`
   3. `{script_name}-{MLC_HOST_OS_FLAVOR}-{MLC_HOST_PLATFORM_FLAVOR}.sh`
   4. `{script_name}-{MLC_HOST_OS_FLAVOR}.sh`
   5. `{script_name}-{MLC_HOST_OS_FLAVOR_LIKE}-{MLC_HOST_PLATFORM_FLAVOR}.sh`
   6. `{script_name}-{MLC_HOST_OS_FLAVOR_LIKE}.sh`
   7. `{script_name}-{MLC_HOST_OS_TYPE}-{MLC_HOST_PLATFORM_FLAVOR}.sh`
   8. `{script_name}-{MLC_HOST_OS_TYPE}.sh`
   9. `{script_name}-{MLC_HOST_PLATFORM_FLAVOR}.sh`
   10. `{script_name}.sh` (fallback)

3. **Returns the First Matching File**  
   - If a file is found in the given priority order, it returns the full path.
   - If no prefixed script exists, it returns `{path}/{script_name}.sh`.

---

### **Example Usage**
#### **Example 1: Finding the Most Specific Script**
📌 **Environment Variables**
```python
env = {
    'MLC_HOST_OS_FLAVOR': 'ubuntu',
    'MLC_HOST_OS_FLAVOR_LIKE': 'debian',
    'MLC_HOST_OS_TYPE': 'linux',
    'MLC_HOST_OS_VERSION': '20.04',
    'MLC_HOST_PLATFORM_FLAVOR': 'x86_64'
}
```
📂 **Available Files in `/scripts/`**
```
run-ubuntu-20.04-x86_64.sh
run-ubuntu-20.04.sh
run.sh
```
🔍 **Function Call**
```python
get_script_name(env, "/scripts")
```
✅ **Output**
```python
"/scripts/run-ubuntu-20.04-x86_64.sh"
```
✔ **Explanation**: The function finds `"run-ubuntu-20.04-x86_64.sh"` as it has the highest priority.

---

#### **Example 2: Fallback When Some Variables Are Missing**
📌 **Environment Variables**
```python
env = {
    'MLC_HOST_OS_FLAVOR_LIKE': 'debian',
    'MLC_HOST_OS_TYPE': 'linux',
    'MLC_HOST_PLATFORM_FLAVOR': 'arm64'
}
```
📂 **Available Files in `/scripts/`**
```
run-debian-arm64.sh
run.sh
```
🔍 **Function Call**
```python
get_script_name(env, "/scripts")
```
✅ **Output**
```python
"/scripts/run-debian-arm64.sh"
```
✔ **Explanation**: Since `MLC_HOST_OS_FLAVOR` is missing, the function falls back to `MLC_HOST_OS_FLAVOR_LIKE` and selects `"run-debian-arm64.sh"`.

---

#### **Example 3: No Prefixed Scripts Exist**
📌 **Environment Variables**
```python
env = {
    'MLC_HOST_OS_TYPE': 'linux'
}
```
📂 **Available Files in `/scripts/`**
```
run.sh
```
🔍 **Function Call**
```python
get_script_name(env, "/scripts")
```
✅ **Output**
```python
"/scripts/run.sh"
```
✔ **Explanation**: Since no prefixed scripts exist, the function returns the default `"run.sh"`.

