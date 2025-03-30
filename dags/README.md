# USER CODE, DAEMON AND WEB SERVER IMAGES

```bash
#/bin/bash

## Building
IMAGE_NAME_USER_CODE="docker_example_user_code_image"
IMAGE_NAME_DAEMON="docker_example_daemon"
IMAGE_NAME_WEB_SERVER="docker_example_webserver"
IMAGE_TAG="latest"

docker build -t $IMAGE_NAME_USER_CODE:$IMAGE_TAG -f Dockerfile_user_code .
docker build --target daemon -t $IMAGE_NAME_DAEMON:$IMAGE_TAG -f Dockerfile_dagster .
docker build --target webserver -t $IMAGE_NAME_WEB_SERVER:$IMAGE_TAG -f Dockerfile_dagster .

## Running locally each container separetately
## IMPORTANT: --network host is only available in Linux
## DATABASE RUNNING IN LOCAL MACHINE: create user and database
docker run --rm --network host $IMAGE_NAME_USER_CODE:$IMAGE_TAG
#
docker run --rm \
           -e DAGSTER_POSTGRES_HOST="localhost" \
           -e DAGSTER_POSTGRES_USER="postgres_user" \
           -e DAGSTER_POSTGRES_PASSWORD="postgres_password" \
           -e DAGSTER_POSTGRES_DB="postgres_db" \
           -e DAGSTER_POSTGRES_PORT=5432 \
           -e USER_CODE_HOST="localhost" \
           -e USER_CODE_PORT=4000 \
           -e RUN_TYPE="DAEMON" \
           --network host \
           $IMAGE_NAME_DAEMON:$IMAGE_TAG

#
docker run --rm \
           -e DAGSTER_POSTGRES_HOST="localhost" \
           -e DAGSTER_POSTGRES_USER="postgres_user" \
           -e DAGSTER_POSTGRES_PASSWORD="postgres_password" \
           -e DAGSTER_POSTGRES_DB="postgres_db" \
           -e DAGSTER_POSTGRES_PORT=5432 \
           -e USER_CODE_HOST="localhost" \
           -e USER_CODE_PORT=4000 \
           -e RUN_TYPE="WEBSERVER" \
           --network host \
           $IMAGE_NAME_WEB_SERVER:$IMAGE_TAG

# GO TO localhost:3000

## Pushing each image into ACR
## ADMIN USER MUST BE ENABLED
ACR_LOGIN_SERVER=""

# USER CODE
docker tag $IMAGE_NAME_USER_CODE:$IMAGE_TAG $ACR_LOGIN_SERVER/$IMAGE_NAME_USER_CODE:$IMAGE_TAG
docker push $ACR_LOGIN_SERVER/$IMAGE_NAME_USER_CODE:$IMAGE_TAG

# DAEMON
docker tag $IMAGE_NAME_DAEMON:$IMAGE_TAG $ACR_LOGIN_SERVER/$IMAGE_NAME_DAEMON:$IMAGE_TAG
docker push $ACR_LOGIN_SERVER/$IMAGE_NAME_DAEMON:$IMAGE_TAG

# WEB SERVER
docker tag $IMAGE_NAME_WEB_SERVER:$IMAGE_TAG $ACR_LOGIN_SERVER/$IMAGE_NAME_WEB_SERVER:$IMAGE_TAG
docker push $ACR_LOGIN_SERVER/$IMAGE_NAME_WEB_SERVER:$IMAGE_TAG

```