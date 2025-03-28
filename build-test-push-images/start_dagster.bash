#!/bin/bash

# Check if dagster_config_source.yaml exists
if [ ! -f "dagster_config_source.yaml" ]; then
  echo "[ERROR] dagster_config_source.yaml file not found!"
  exit 1
fi

# Read the whole content of dagster_config_source.yaml
dagster_config_content=$(cat dagster_config_source.yaml)

cat dagster_config_source.yaml | envsubst > dagster.yaml

echo "[INFO] dagster.yaml has been created with the provided configuration."

if [ "$RUN_TYPE" = "WEBSERVER" ]; then
    dagster-webserver -h 0.0.0.0 -p 3000 -w workspace.yaml
elif [ "$RUN_TYPE" = "DAEMON" ]; then
    dagster-daemon run
else
    echo "[ERROR] RUN_TYPE must be set as env varieble. It should be either WEBSERVER or DAEMON"
fi
