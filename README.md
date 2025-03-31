# Azure Dagster Infrastructure with Pulumi

## UPDATE ME!!
After overhauling the repo, the readme is not yet updated.  update before sharing!

## Overview
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



## Pulumi Code
Before running Pulumi code:
### Images
- Building, test (locally) and push images into registry (creation in next point), follow `README.md` in `build-test-push-images` folder.
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

## More Info
### Docker Compose Deployment
https://docs.dagster.io/guides/deploy/deployment-options/docker
### ECS Deployment
https://docs.dagster.io/guides/deploy/deployment-options/aws#deploying-in-ecs
### Dagster YAML Reference
https://docs.dagster.io/guides/deploy/dagster-yaml
### Handle Secrets
https://docs.dagster.io/guides/deploy/using-environment-variables-and-secrets#handling-secrets
