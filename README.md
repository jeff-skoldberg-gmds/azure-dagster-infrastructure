# greenmountain-dagster-container

# Overview
* Steps to create ACR, build, test and push images: `build-test-push-images/`
* Pulumi code: `azure-dagster`
    - 1 Resource Group
    - 1 Azure Cosmos DB for PostgreSQL Cluster
    - 1 Container Apps Environment
    - 1 Log Analytics workspace
    - 3 Container Apps: user code, daermon and webserver
    - 1 User Assigned Identity to pull images from ACR
    ![IMAGE](/assets/02.resources.png)

## Prerequisites
- Install Python 
- Install AZ CLI: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
- Install Pulumi: https://www.pulumi.com/docs/iac/get-started/azure/begin/

## Basic Tutorial
- Create project: https://www.pulumi.com/docs/iac/get-started/azure/create-project/
- Follow documentation to preview, update, deploy and destroy project

## Pulumi Code
Before running Pulumi code:
### Images
- Bilding, test (locally) and push images into registry (creation in next point), follow `README.md` in `build-test-push-images` folder.
### Azure Container Registry
```bash
#!/bin/bash

# CREATE RESOURCE GROUP
ACR_RG="acrtestdelete"
ACR_RG_LOCATION="eastus"
az group create --name $ACR_RG --location $ACR_RG_LOCATION

# CREATE ACR
ACR_NAME="containeregtest"
az acr create --resource-group $ACR_RG --name $ACR_NAME --sku Basic

# LOGIN INTO ACR
az acr login --name $ACR_NAME
```

### Pulumi Code
```bash
pulumi refresh

# Choose stack or create a new one
pulumi up

# Delete
pulumi destroy
```

### Known Issues:
* ENVIRONMENT VARIABLES:
    - Even though env variables are set, you see that the following environment variables are not available (`build-test-push-images/dagster.yaml`):
    ```bash
    postgres_db:
        hostname:
        env: DAGSTER_POSTGRES_HOST
        username:
        env: DAGSTER_POSTGRES_USER
        password:
        env: DAGSTER_POSTGRES_PASSWORD
        db_name:
        env: DAGSTER_POSTGRES_DB
        port:
        env: DAGSTER_POSTGRES_PORT
    ```
    ![IMAGE](/assets/01.env.png)
    - [GitHub Issue](https://github.com/dagster-io/dagster/issues/3013)
    - I'd need to research a solution for this, since locally `dagster.yaml` is taking env variables but not in Azure. For now, a simple solution should be hard code values, rebuild and push images.


## More Info
### Docker Compose Deployment
https://docs.dagster.io/guides/deploy/deployment-options/docker
### ECS Deployment
https://docs.dagster.io/guides/deploy/deployment-options/aws#deploying-in-ecs
### Dagster YAML Reference
https://docs.dagster.io/guides/deploy/dagster-yaml
### Handle Secrets
https://docs.dagster.io/guides/deploy/using-environment-variables-and-secrets#handling-secrets
