"""An Azure RM Python Pulumi program"""

import pulumi
from pulumi_azure_native import app
from pulumi_azure_native import containerregistry
from pulumi_azure_native import resources
from pulumi_azure_native import operationalinsights
from pulumi_azure_native import managedidentity
from pulumi_azure_native import authorization
from pulumi_azure_native import dbforpostgresql
from pulumi_docker import Image, DockerBuild, ImageRegistry
from pulumi_azure_native.containerregistry import list_registry_credentials_output

# Get config values
config = pulumi.Config()
ACR_RG = config.require("ACR_RG")
ACR_NAME = config.require("ACR_NAME")
IMAGE_TAG = config.require("IMAGE_TAG")
IMAGE_NAME_USER_CODE = config.require("IMAGE_NAME_USER_CODE")
IMAGE_NAME_DAEMON = config.require("IMAGE_NAME_DAEMON")
IMAGE_NAME_WEB_SERVER = config.require("IMAGE_NAME_WEB_SERVER")
SUBSCRIPTION_ID = config.require("SUBSCRIPTION_ID")
DAGSTER_POSTGRES_PASSWORD = config.require_secret("DAGSTER_POSTGRES_PASSWORD")
DAGSTER_POSTGRES_PORT = config.require("DAGSTER_POSTGRES_PORT")
USER_CODE_PORT = config.require("USER_CODE_PORT")

# Resource Group with proper Output handling
resource_group = resources.ResourceGroup(
    "dagsterResourceGroup",
    resource_group_name=ACR_RG,
    location="eastus"  # or your preferred Azure region
)

# Azure Cosmos DB for PostgreSQL cluster

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
acr = containerregistry.Registry(
    "acr",
    registry_name=ACR_NAME,
    resource_group_name=resource_group.name,
    location=resource_group.location,
    sku=containerregistry.SkuArgs(
        name="Basic"
    ),
    admin_user_enabled=True,
    opts=pulumi.ResourceOptions(parent=resource_group)
)

acr_credentials = list_registry_credentials_output(
    resource_group_name=resource_group.name,
    registry_name=acr.name
)

acr_username = acr_credentials.username
acr_password = acr_credentials.passwords[0].value

user_code_image = Image(
    "userCodeImage",
    build=DockerBuild(context="./user_code"),
    image_name=acr.login_server.apply(lambda r: f"{r}/docker_example_user_code_image:{IMAGE_TAG}"),
    registry=ImageRegistry(
        server=acr.login_server,
        username=acr_username,
        password=acr_password,
    ),
)
daemon_image = Image(
    "daemonImage",
    build=DockerBuild(context="./daemon"),
    image_name=acr.login_server.apply(lambda r: f"{r}/docker_example_daemon:{IMAGE_TAG}"),
    registry=ImageRegistry(
        server=acr.login_server,
        username=acr_username,
        password=acr_password,
    ),
)
web_server_image = Image(
    "webServerImage",
    build=DockerBuild(context="./web_server"),
    image_name=acr.login_server.apply(lambda r: f"{r}/docker_example_webserver:{IMAGE_TAG}"),
    registry=ImageRegistry(
        server=acr.login_server,
        username=acr_username,
        password=acr_password,
    ),
)


# Update acr_o references to use the new acr resource
acr_o = pulumi.Output.from_input(acr)

# Container Apps
## Role to pull image from ACR
container_app_identity = managedidentity.UserAssignedIdentity(
    "userAssignedIdentity",
    location=resource_group.location,
    resource_group_name=resource_group.name,
    resource_name_="acrpullidentity",
    tags={
        "Environment": "Production"
    })

acr_pull_built_in_id = pulumi.Output.concat(
    "/subscriptions/", 
    SUBSCRIPTION_ID, 
    "/providers/Microsoft.Authorization/roleDefinitions/7f951dda-4ed3-4680-a7ca-43fe172d538d"
)

acr_pull_assignment = authorization.RoleAssignment(
    "acrPullAssignment",
    principal_id=container_app_identity.principal_id,
    principal_type=authorization.PrincipalType.SERVICE_PRINCIPAL,
    role_definition_id=acr_pull_built_in_id,
    scope=acr_o.apply(lambda x: x.id),
)

# Update container image references
def get_container_image(acr_login_server, image_name, tag):
    return pulumi.Output.concat(acr_login_server, "/", image_name, ":", tag)

# Update user code app
user_code_app = app.ContainerApp(
    "userCodeApp",
    container_app_name="usercode",
    location=resource_group.location,
    resource_group_name=resource_group.name,
    environment_id=container_env.id,
    identity=app.ManagedServiceIdentityArgs(
        type=app.ManagedServiceIdentityType.USER_ASSIGNED,
        user_assigned_identities=[container_app_identity.id]
    ),
    template=app.TemplateArgs(
        containers=[app.ContainerArgs(
            image=pulumi.Output.all(acr.login_server, IMAGE_NAME_USER_CODE, IMAGE_TAG)
                  .apply(lambda args: f"{args[0]}/{args[1]}:{args[2]}"),
            name="usercode",
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

# Update environment variable definitions to handle Output types
DAGSTER_POSTGRES_HOST = single_node_pg_cluster.server_names.apply(
    lambda names: names[0].fully_qualified_domain_name
)
DAGSTER_POSTGRES_USER = "citus"
DAGSTER_POSTGRES_DB = "citus"
USER_CODE_HOST = "usercode"

def make_container_env_vars(postgres_host, postgres_port, user_code_port, postgres_password):
    return [
        app.EnvironmentVarArgs(
            name="DAGSTER_POSTGRES_HOST",
            value=pulumi.Output.from_input(postgres_host)
        ),
        app.EnvironmentVarArgs(
            name="DAGSTER_POSTGRES_USER",
            value=DAGSTER_POSTGRES_USER
        ),
        app.EnvironmentVarArgs(
            name="DAGSTER_POSTGRES_PASSWORD",
            value=postgres_password  # Changed from secret_ref to direct value
        ),
        app.EnvironmentVarArgs(
            name="DAGSTER_POSTGRES_DB",
            value=DAGSTER_POSTGRES_DB
        ),
        app.EnvironmentVarArgs(
            name="DAGSTER_POSTGRES_PORT",
            value=pulumi.Output.from_input(postgres_port)
        ),
        app.EnvironmentVarArgs(
            name="USER_CODE_HOST",
            value=USER_CODE_HOST
        ),
        app.EnvironmentVarArgs(
            name="USER_CODE_PORT",
            value=pulumi.Output.from_input(user_code_port)
        )
    ]

# Update container app templates to use all Output parameters
def get_container_env_vars():
    return pulumi.Output.all(
        DAGSTER_POSTGRES_HOST,
        DAGSTER_POSTGRES_PORT,
        USER_CODE_PORT,
        DAGSTER_POSTGRES_PASSWORD
    ).apply(lambda args: make_container_env_vars(*args))

# Update daemon app
daemon_app = app.ContainerApp(
    "daemonApp",
    container_app_name="daemontwo",
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
            )]
    ),
    template=app.TemplateArgs(
        containers=[app.ContainerArgs(
            image=pulumi.Output.all(acr.login_server, IMAGE_NAME_DAEMON, IMAGE_TAG)
                  .apply(lambda args: f"{args[0]}/{args[1]}:{args[2]}"),
            name="daemontwo",
            env=get_container_env_vars(),
            resources=app.ContainerResourcesArgs(
                cpu=0.75,
                memory="1.5Gi"
            )
        )]
    ))

# Update web server app
web_server_app = app.ContainerApp(
    "webServer",
    container_app_name="webservertwo",
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
            )]
    ),
    template=app.TemplateArgs(
        containers=[app.ContainerArgs(
            image=pulumi.Output.all(acr.login_server, IMAGE_NAME_WEB_SERVER, IMAGE_TAG)
                  .apply(lambda args: f"{args[0]}/{args[1]}:{args[2]}"),
            name="webservertwo",
            env=get_container_env_vars(),
            resources=app.ContainerResourcesArgs(
                cpu=0.75,
                memory="1.5Gi"
            )
        )]
    ))

# Replace existing exports section with comprehensive exports
# Resource Group
pulumi.export("resourceGroupName", resource_group.name)
pulumi.export("resourceGroupId", resource_group.id)

# Postgres
pulumi.export("postgresClusterId", single_node_pg_cluster.id)
pulumi.export("postgresHost", DAGSTER_POSTGRES_HOST)
pulumi.export("postgresFirewallRuleId", firewall_rule.id)

# Container Environment
pulumi.export("containerEnvLogsWorkspaceId", container_env_logs.id)
pulumi.export("containerEnvId", container_env.id)
pulumi.export("containerEnvName", container_env.name)

# ACR
pulumi.export("acrId", acr.id)
pulumi.export("acrLoginServer", acr.login_server)
pulumi.export("acrName", acr.name)

# Identity
pulumi.export("containerAppIdentityId", container_app_identity.id)
pulumi.export("containerAppIdentityPrincipalId", container_app_identity.principal_id)
pulumi.export("containerAppIdentityClientId", container_app_identity.client_id)

# Container Apps
pulumi.export("userCodeAppId", user_code_app.id)
pulumi.export("userCodeAppName", user_code_app.name)
pulumi.export("userCodeAppUrl", 
    user_code_app.configuration.apply(lambda config: config.ingress.fqdn if config.ingress else None))

pulumi.export("daemonAppId", daemon_app.id)
pulumi.export("daemonAppName", daemon_app.name)

pulumi.export("webServerAppId", web_server_app.id)
pulumi.export("webServerAppName", web_server_app.name)
pulumi.export("webServerAppUrl", 
    web_server_app.configuration.apply(lambda config: config.ingress.fqdn if config.ingress else None))

# Role Assignment
pulumi.export("acrPullRoleAssignmentId", acr_pull_assignment.id)
