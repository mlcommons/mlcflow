# Script Meta  

This page provides a walkthrough of the `meta.yaml` file.  

## Important Keys and Data Types  

- **alias** (`string`)  

  - Alias of the script, which can be used instead of tags when running a script.  

- **uid** (`string`)  

  - Unique identifier for individual scripts.  

  - Can be used instead of tags when running a script.  

- **automation_alias** (`string`)  

  - Alias specific to script automation.  

- **automation_uid** (`string`)  

  - Unique identifier for script automation.  

- **category** (`string`)  

  - Defines the script category.  

- **tags** (`list of strings`)  

  - List of tags users can specify to run the script.  

- **default_env** (`dictionary` with `string` values)  

  - Contains key-value pairs representing environment variables and their default values for a script.

  - These default values are overridden if the same environment variable is set in script files or inherited from a parent script.  

- **env** (`dictionary` with `string` values)  

  - Defines environment variables and their corresponding values.  

- **input_mapping** (`dictionary` with `string` values)  

  - Maps input flags related to a script to corresponding environment variables.  

  - Only keys specified under `input_mapping` in `meta.yaml` are mapped to environment variables.  

- **env_key_mapping** (`dictionary` with `string` values)  

  - Maps one environment key to another.  

- **new_env_keys** (`list of strings`)  

  - Specifies environment keys that should be passed to a parent script if this script is used as a dependency.  

- **new_state_keys** (`list of strings`)  

  - Specifies state keys that should be passed to a parent script when used as a dependency.  

- **add_deps_recursive** (`dictionary`)  

  - Customizes recursive dependencies with nested `tags` and other attributes.  

### Dependencies  

  Dependencies in a script are specified as a list of dictionaries.

  - Each dictionary can contain:

    - **tags**

      - Comma separated list of tags to identify a dependent script

    - **names** (`list of strings`)

      - Identifiers for dependencies, allowing users to modify the deps executions when needed.  

    - **enable_if_env** (`dictionary` with `list of strings` values)  

      - Specifies conditions under which a dependency is enabled based on environment variables. The conditions are ANDed. 

    - **enable_if_any_env** (`dictionary` with `list of strings` values)  

      - Specifies conditions under which a dependency is enabled based on environment variables. The conditions are ORed.

    - **skip_if_env** (`dictionary` with `list of strings` values)  

      - Specifies conditions under which a dependency should be skipped. The conditions are ANDed.

    - **skip_if_any_env** (`dictionary` with `list of strings` values)  

      - Specifies conditions under which a dependency should be skipped. The conditions are ORed.

    - Any other script meta can also be included which will be passed to the dependent script

  In MLC script, there are four types of dependencies.

  - **deps**

    - Executes after processing the script meta, but before the `preprocess` function

  - **prehook_deps**

    - Executes after the `preprocess` function, but before the `run` script

  - **posthook_deps**

    - Executes after the `run` script, but before the `postprocess` function

  - **post_deps**

    - Executes after the `postprocess` function

  More details on script execution flow can be found [here](execution-flow.md).


### Variation Configuration  

- **variations** (`dictionary`)  
 
  - Contains script variations, including attributes like `alias`, `default_variations`, and `group`.  

- **group** (`string`)  

  - Specifies the script variation group. Maximum one variation from a given group can be selected during a script invocation and if `default:true` is set for a variation in a group, that variation is turned on unless another variation is specified during the script invocation.

- **default_variations** (`dictionary` with `string` values)  

  - Specifies default variations for the script.  



### Docker Configuration  

- **docker** (`dictionary`)  

  - Contains Docker-specific configurations:  

    - **base_image** (`string`) – Base Docker image  

    - **image_name** (`string`) – Docker image name  

    - **os** (`string`) – Operating system  

    - **os_version** (`string`) – OS version  

    - **deps** (`list of dictionaries`) – Specifies dependencies required in Docker  

    - **env** (`dictionary` with `string` values) – Defines environment variables inside the container  

    - **interactive** (`boolean`) – Indicates if the container should be interactive  

    - **extra_run_args** (`string`) – Additional arguments for `docker run`  

    - **mounts** (`list of strings`) – Specifies mount paths in the format `"source:destination"`  

    - **pre_run_cmds** (`list of strings`) – Commands to execute before starting the container  

    - **docker_input_mapping** (`dictionary` with `string` values) – Maps input parameters to Docker environment variables  

    - **use_host_user_id** (`boolean`) – Uses the host's user ID inside the container  

    - **use_host_group_id** (`boolean`) – Uses the host's group ID inside the container  

    - **skip_run_cmd** (`string`) – Command to skip execution  

    - **shm_size** (`string`) – Defines shared memory size  

    - **real_run** (`boolean`) – Indicates if the container should do the MLC script run at end, if not only the deps will be run

    - **all_gpus** (`string`) – Use all available GPUs

---

