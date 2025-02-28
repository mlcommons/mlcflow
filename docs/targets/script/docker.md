# Docker Script

**MLCFlow** enables a MLC script to be run inside a docker container. This increases the amount of reproducibility that could be achieved by keeping the execution environment similar.

## **Syntax Variations**

A MLCFlow script can be executed inside a docker container through either of the following syntaxes

1. **Docker Run:** `mlc docker run --tags=<script tags> <run flags>` (e.g., `mlc docker run --tags=detect,os --docker_dt --docker_cache=no`)  
2. **Docker Script:** `mlc docker script --tags=<script tags> <run flags>` (e.g., `mlc docker script --tags=detect,os --docker_dt --docker_cache=no`)  

## **Flags Available**

- **`--docker_dt` or  `--docker_detached`:** 
    - Runs the script specified inside a docker container in detached mode. (e.g., `mlc docker run --tags=detect,os --docker_dt).
    - By default, docker container gets launched in interactive mode.
- **`--docker_cache`:** 
    - Disabling the use of docker cache will make docker to build all the layers from scratch, ignoring previously cached layers. (e.g., `mlc docker run --tags=detect,os --docker_cache=no`)  
    - By default, the value is set to true/yes.
- **`--docker_rebuild`:** 
    - Enabling this flag would rebuild the docker container even if there are any existing containers with the same tag. (e.g., `mlc docker run --tags=detect,os --docker_rebuild`)  
    - By default, the value is set to False.
- **`--dockerfile_recreate`:** 
    - Enabling this flag would recreate dockerfile on docker run. (e.g., `mlc docker run --tags=detect,os --docker_rebuild --dockerfile_recreate`)  
    - By default, the value is set to False.


For more more information about the docker configuration inside `meta.yaml` file, please visit the [Script Meta](meta.md#docker-configuration) page.
