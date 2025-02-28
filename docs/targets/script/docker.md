# Docker Script

**MLCFlow** enables an MLC script to be run inside a docker container,  enhancing reproducibility by maintaining a consistent execution environment.

## **Syntax Variations**

An MLCFlow script can be executed inside a Docker container using either of the following syntaxes:

1. **Docker Run:** `mlc docker run --tags=<script tags> <run flags>` (e.g., `mlc docker run --tags=detect,os --docker_dt --docker_cache=no`)  
2. **Docker Script:** `mlc docker script --tags=<script tags> <run flags>` (e.g., `mlc docker script --tags=detect,os --docker_dt --docker_cache=no`)  

## **Flags Available**

- **`--docker_dt` or  `--docker_detached`:** 
    - Runs the specified script inside a Docker container in detached mode (e.g., `mlc docker run --tags=detect,os --docker_dt).
    - By default, the Docker container is launched in interactive mode.
- **`--docker_cache`:** 
    - Disabling the use of the Docker cache will force Docker to build all layers from scratch, ignoring previously cached layers (e.g., `mlc docker run --tags=detect,os --docker_cache=no`)  
    - By default, the value is set to true/yes.
- **`--docker_rebuild`:** 
    - Enabling this flag will rebuild the Docker container even if there are existing containers with the same tag. (e.g., `mlc docker run --tags=detect,os --docker_rebuild`)  
    - By default, the value is set to False.
- **`--dockerfile_recreate`:** 
    - Enabling this flag will recreate the Dockerfile on Docker run (e.g., `mlc docker run --tags=detect,os --docker_rebuild --dockerfile_recreate`)  
    - By default, the value is set to False.


For more information about the Docker configuration inside the  `meta.yaml` file, please visit the [Script Meta](meta.md#docker-configuration) page.
