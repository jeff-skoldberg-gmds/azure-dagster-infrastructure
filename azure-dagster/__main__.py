"""An Azure RM Python Pulumi program"""

import os
import pulumi
from pulumi_azure_native import app
from pulumi_azure_native import containerregistry
from pulumi_azure_native import resources
from pulumi_azure_native import operationalinsights
from pulumi_azure_native import managedidentity
from pulumi_azure_native import authorization
from pulumi_azure_native import dbforpostgresql

# Resource Group
resource_group = resources.ResourceGroup("deletsfsdelater")

# Azure Cosmos DB for PostgreSQL cluster
DAGSTER_POSTGRES_PASSWORD = os.environ["DAGSTER_POSTGRES_PASSWORD"]

single_node_pg_cluster = dbforpostgresql.Cluster(
    "clusterSingleNode",
    cluster_name="testcluster-burstablev1",
    location=resource_group.location,
    resource_group_name=resource_group.name,
    administrator_login_password=DAGSTER_POSTGRES_PASSWORD,
    citus_version="11.3",
    coordinator_enable_public_ip_access=True,
    coordinator_server_edition="BurstableMemoryOptimized",
    coordinator_v_cores=1,
    coordinator_storage_quota_in_mb=32768,
    node_count=0,
    enable_ha=False,
    enable_shards_on_coordinator=True,
    postgresql_version="15",
    preferred_primary_zone="1",
    tags={
        "Environment": "Prod",
    })

firewall_rule = dbforpostgresql.v20221108.FirewallRule(
    "firewallRule",
    firewall_rule_name="rule1",
    cluster_name=single_node_pg_cluster.name,
    resource_group_name=resource_group.name,
    start_ip_address="0.0.0.0",
    end_ip_address="255.255.255.255",
    opts=pulumi.ResourceOptions(depends_on=[single_node_pg_cluster]))

# Container Environment
## Logs
container_env_logs = operationalinsights.Workspace("workspace",
    workspace_name="acctest-01",
    location=resource_group.location,
    resource_group_name=resource_group.name,
    sku={
        "name": operationalinsights.WorkspaceSkuNameEnum.PER_GB2018
    },
    retention_in_days=30)

## Environment
log_shared_keys_o = operationalinsights.get_workspace_shared_keys_output(
    resource_group_name=resource_group.name,
    workspace_name=container_env_logs.name
)

container_env = app.ManagedEnvironment(
    "managedEnvironmentResource",
    location=resource_group.location,
    resource_group_name=resource_group.name,
    environment_name="deetelateenvadf",
    sku=app.EnvironmentSkuPropertiesArgs(name=app.SkuName.CONSUMPTION),
    app_logs_configuration=app.AppLogsConfigurationArgs(
        destination="log-analytics",
        log_analytics_configuration=app.LogAnalyticsConfigurationArgs(
            customer_id=container_env_logs.customer_id,
            shared_key=log_shared_keys_o.apply(lambda keys: keys.primary_shared_key),
        )
    ),
    tags={"Environment": "Production"},
    zone_redundant=False,  # Optional: Set to True for zone-redundant if needed
)

# ACR
ACR_NAME = os.getenv("ACR_NAME")
ACR_RG = os.getenv("ACR_RG")
acr_o = containerregistry.get_registry_output(
    registry_name=ACR_NAME,
    resource_group_name=ACR_RG)

# Container Apps
IMAGE_TAG = os.getenv("IMAGE_TAG")

## Role to pull image from ACR
container_app_identity = managedidentity.UserAssignedIdentity(
    "userAssignedIdentity",
    location=resource_group.location,
    resource_group_name=resource_group.name,
    resource_name_="acrpullidentity",
    tags={
        "Environment": "Production"
    })

SUBSCRIPTION_ID = os.getenv("SUBSCRIPTION_ID")
acr_pull_built_in_id = f"/subscriptions/{SUBSCRIPTION_ID}/providers/Microsoft.Authorization/roleDefinitions/7f951dda-4ed3-4680-a7ca-43fe172d538d"

acr_pull_assignment = authorization.RoleAssignment(
    "acrPullAssignment",
    principal_id=container_app_identity.principal_id,
    principal_type=authorization.PrincipalType.SERVICE_PRINCIPAL,
    role_definition_id=acr_pull_built_in_id,
    scope=acr_o.apply(lambda x: x.id),
)

## Container Apps - User Code
IMAGE_NAME_USER_CODE = os.getenv("IMAGE_NAME_USER_CODE")
USER_CODE_APP_NAME = "usercode"
user_code_app = app.ContainerApp(
    "userCodeApp",
    container_app_name=USER_CODE_APP_NAME,
    location=resource_group.location,
    resource_group_name=resource_group.name,
    environment_id=container_env.id,
    identity=app.ManagedServiceIdentityArgs(
        type=app.ManagedServiceIdentityType.USER_ASSIGNED,
        user_assigned_identities=[container_app_identity.id]
    ),
    template=app.TemplateArgs(
        containers=[app.ContainerArgs(
            image=acr_o.apply(lambda x: f"{x.login_server}/{IMAGE_NAME_USER_CODE}:{IMAGE_TAG}"),
            name=USER_CODE_APP_NAME,
            resources=app.ContainerResourcesArgs(
                cpu=0.75,
                memory="1.5Gi"
            )
        )]
    ),
    configuration=app.ConfigurationArgs(
        ingress=app.IngressArgs(
            external=False,
            transport= app.IngressTransportMethod.TCP,
            exposed_port=4000,
            target_port=4000,
            allow_insecure=False
        ),
        registries=[
            app.RegistryCredentialsArgs(
                identity=container_app_identity.id,
                server=acr_o.apply(lambda x: x.login_server)
            )]
    ))

DAGSTER_POSTGRES_HOST = single_node_pg_cluster.server_names[0].fully_qualified_domain_name
DAGSTER_POSTGRES_USER = "citus" # Using default admin user
DAGSTER_POSTGRES_DB = "citus" # Using default DB
DAGSTER_POSTGRES_PORT = os.environ["DAGSTER_POSTGRES_PORT"]
USER_CODE_HOST = "usercode" # Harcoded value, possible solution below:
# USER_CODE_HOST = user_code_app.configuration.apply(lambda config: config.ingress.fqdn)
USER_CODE_PORT = os.environ["USER_CODE_PORT"]

## Container Apps - Daemon
IMAGE_NAME_DAEMON = os.getenv("IMAGE_NAME_DAEMON")
DAEMON_APP_NAME = "daemontwo"
daemon_app = app.ContainerApp(
    "daemonApp",
    container_app_name=DAEMON_APP_NAME,
    location=resource_group.location,
    resource_group_name=resource_group.name,
    environment_id=container_env.id,
    identity=app.ManagedServiceIdentityArgs(
        type=app.ManagedServiceIdentityType.USER_ASSIGNED,
        user_assigned_identities=[container_app_identity.id]
    ),
    configuration=app.ConfigurationArgs(
        registries=[
            app.RegistryCredentialsArgs(
                identity=container_app_identity.id,
                server=acr_o.apply(lambda x: x.login_server)
            )],
        secrets=[app.SecretArgs(
            name="db-postgres-pwd",
            value=DAGSTER_POSTGRES_PASSWORD
        )]
    ),
    template=app.TemplateArgs(
        containers=[app.ContainerArgs(
            image=acr_o.apply(lambda x: f"{x.login_server}/{IMAGE_NAME_DAEMON}:{IMAGE_TAG}"),
            name=DAEMON_APP_NAME,
            env=[
                app.EnvironmentVarArgs(
                    name="DAGSTER_POSTGRES_HOST",
                    value=DAGSTER_POSTGRES_HOST,
                ),
                app.EnvironmentVarArgs(
                    name="DAGSTER_POSTGRES_USER",
                    value=DAGSTER_POSTGRES_USER
                ),
                app.EnvironmentVarArgs(
                    name="DAGSTER_POSTGRES_PASSWORD",
                    secret_ref="db-postgres-pwd"
                ),
                app.EnvironmentVarArgs(
                    name="DAGSTER_POSTGRES_DB",
                    value=DAGSTER_POSTGRES_DB,
                ),
                app.EnvironmentVarArgs(
                    name="DAGSTER_POSTGRES_PORT",
                    value=DAGSTER_POSTGRES_PORT,
                ),
                app.EnvironmentVarArgs(
                    name="USER_CODE_HOST",
                    value=USER_CODE_HOST,
                ),
                app.EnvironmentVarArgs(
                    name="USER_CODE_PORT",
                    value=USER_CODE_PORT,
                )
            ],
            resources=app.ContainerResourcesArgs(
                cpu=0.75,
                memory="1.5Gi"
            )
        )]
    ))

## Container Apps - Web Server
IMAGE_NAME_WEB_SERVER = os.getenv("IMAGE_NAME_WEB_SERVER")
WEB_SERVER_APP_NAME = "webservertwo"
web_server_app = app.ContainerApp(
    "webServer",
    container_app_name=WEB_SERVER_APP_NAME,
    location=resource_group.location,
    resource_group_name=resource_group.name,
    environment_id=container_env.id,
    identity=app.ManagedServiceIdentityArgs(
        type=app.ManagedServiceIdentityType.USER_ASSIGNED,
        user_assigned_identities=[container_app_identity.id]
    ),
    configuration=app.ConfigurationArgs(
        ingress=app.IngressArgs(
            external=True,
            transport= app.IngressTransportMethod.HTTP,
            target_port=3000,
            allow_insecure=False
        ),
        registries=[
            app.RegistryCredentialsArgs(
                identity=container_app_identity.id,
                server=acr_o.apply(lambda x: x.login_server)
           )],
        secrets=[app.SecretArgs(
            name="db-postgres-pwd",
            value=DAGSTER_POSTGRES_PASSWORD
        )]
    ),
    template=app.TemplateArgs(
        containers=[app.ContainerArgs(
            image=acr_o.apply(lambda x: f"{x.login_server}/{IMAGE_NAME_WEB_SERVER}:{IMAGE_TAG}"),
            name=WEB_SERVER_APP_NAME,
            env=[
                app.EnvironmentVarArgs(
                    name="DAGSTER_POSTGRES_HOST",
                    value=DAGSTER_POSTGRES_HOST,
                ),
                app.EnvironmentVarArgs(
                    name="DAGSTER_POSTGRES_USER",
                    value=DAGSTER_POSTGRES_USER
                ),
                app.EnvironmentVarArgs(
                    name="DAGSTER_POSTGRES_PASSWORD",
                    secret_ref="db-postgres-pwd"
                ),
                app.EnvironmentVarArgs(
                    name="DAGSTER_POSTGRES_DB",
                    value=DAGSTER_POSTGRES_DB,
                ),
                app.EnvironmentVarArgs(
                    name="DAGSTER_POSTGRES_PORT",
                    value=DAGSTER_POSTGRES_PORT,
                ),
                app.EnvironmentVarArgs(
                    name="USER_CODE_HOST",
                    value=USER_CODE_HOST,
                ),
                app.EnvironmentVarArgs(
                    name="USER_CODE_PORT",
                    value=USER_CODE_PORT,
                )
            ],
            resources=app.ContainerResourcesArgs(
                cpu=0.75,
                memory="1.5Gi"
            )
        )]
    ))

pulumi.export(
    "webServerPublicUrl", 
    web_server_app.configuration.apply(lambda config: config.ingress.fqdn))

pulumi.export(
    "userCodeAppPublicUrl", 
    user_code_app.configuration.apply(lambda config: config.ingress.fqdn))
