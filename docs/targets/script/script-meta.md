This page provides a walkthrough of the `meta.yaml` file.

## Keys and Datatypes followed

1. **alias**: `string`
    - Contains alias of the script which would be used instead of tags while runnning a script.
2. **uid**: `string`
    - Unique identifier used to identify individual scripts. 
    - Could be used instead of tags while running a script
3. **automation_alias**: `string`
    - Alias with respect to particular automation
4. **automation_uid**: `string`
    - Unique identifier used to identify an automation
5. **category**: `string`
    - Script category
6. **developers**: `list of strings`
    - List of developers who were involved in developing the particular script
7. **tags**: `list of strings`
    - List of tags which could be specified by the user to run the particular script
8. **default_env**: `dictionary` - Contains key-value pairs where values are `strings`
    - Contains key-value pairs which depicts the env variable and their value which could be set as default for a particular script.
    - The value of any default env would be replaced if the env variable is set anywhere in script files or is populated from the parent script to child.
9. **env**: `dictionary` - Contains key-value pairs where values are `strings`
    - This key could be used to set a series of env variable and their values.
10. **input_mapping**: `dictionary` - Contains key-value pairs where values are `strings`
    - This helps to map the input flags related to a particular script to the corresponding env variable
    - Only the keys that are specified under `input_mapping` in `meta.yml` of a script are being mapped to env variable.
11. **env_key_mapping**: `dictionary` - Contains key-value pairs where values are `strings`
    - Used to map a particular env key to another env key.
12. **new_env_keys**: `list of strings`
    - Used to specify the env keys that should be passed to the parent script(if the particular script is called as a dependency of another script).
13. **new_state_keys**: `list of strings`
    - Used to specify the state keys that should be passed to the parent script(if the particular script is called as a dependency of another script).
14. **deps**: `list of dictionaries` - Each dictionary can contain `tags` or other nested keys
    - List of dictionaries which specify the tags of the scripts that should be called as a dependency, env variable that should be passed, version, names, etc
    1.  **names**: `list of strings`
        - They are the list of strings that the user could specify for that particular dependency so that whenever user needs to explicitely modify the configuration to be passed for that particular script, they could access through this name. 
    2. **enable_if_env**: `dictionary` - Contains key-value pairs where values are lists of `strings`
        - This key could be used to configure script such that the particular dependency should only be called if one/more env variables are enabled, or their value is set to something specific. 
    3. **skip_if_env**: `dictionary` - Contains key-value pairs where values are lists of `strings`.
        - This key could be used to configure script such that the particular dependency should be skipped if one/more env variables are enabled, or their value is set to something specific. 
15. **prehook_deps**: `list of dictionaries` - Each dictionary may contain `names` and `tags` as lists
    - List of dictionaries which specify the tags of the scripts that should be called as a prehook dependency, env variable that should be passed, version, names, etc
    - To know more about the script execution flow, please see [this](../script-flow/index.md) documentation.
19. **posthook_deps**: `list of dictionaries` - Each dictionary may contain `tags` and other keys
    - List of dictionaries which specify the tags of the scripts that should be called as a posthook dependency, env variable that should be passed, version, names, etc
    - To know more about the script execution flow, please see [this](../script-flow/index.md) documentation.
20. **variation_groups_order**: `list of strings`
21. **variations**: `dictionary` - Each variation is a dictionary containing keys like `alias`, `default_variations`, `group`, etc.
22. **group**: `string`
23. **add_deps_recursive**: `dictionary` - Contains nested `tags` and other keys
24. **default_variations**: `dictionary` - Contains key-value pairs where values are `strings`
25. **docker**: `dictionary` - Contains keys specific to Docker configurations:
    - **base_image**: `string`
    - **image_name**: `string`
    - **os**: `string`
    - **os_version**: `string`
    - **deps**: `list of dictionaries` - Each dictionary can include `tags` or other keys.
    - **env**: `dictionary` - Contains key-value pairs where values are `strings`
    - **interactive**: `boolean`
    - **extra_run_args**: `string`
    - **mounts**: `list of strings` - Specifies mount paths in the format `"source:destination"`
    - **pre_run_cmds**: `list of strings` - Commands to run before the container starts
    - **docker_input_mapping**: `dictionary` - Contains key-value pairs where values are strings, mapping input parameters to Docker environment variables
    - **use_host_user_id**: `boolean`
    - **use_host_group_id**: `boolean`
    - **skip_run_cmd**: `string`
    - **shm_size**: `string`
    - **real_run**: `boolean`
    - **all_gpus**: `string`
