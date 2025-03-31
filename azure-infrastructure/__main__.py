"""An Azure RM Python Pulumi program"""

import pulumi
from pulumi_azure_native import app
from pulumi_azure_native import containerregistry
from pulumi_azure_native import resources
from pulumi_azure_native import operationalinsights
from pulumi_azure_native import managedidentity
from pulumi_azure_native import authorization
from pulumi_azure_native import dbforpostgresql
from pulumi_docker import Image
from pulumi_docker import DockerBuildArgs
from pulumi_random import RandomString


# Get config values
config = pulumi.Config()
DAGSTER_RG = config.require("DAGSTER_RG")
ENV = config.require("ENV")
ACR_NAME= config.require("ACR_NAME")
DAGSTER_POSTGRES_PASSWORD = config.require_secret("DAGSTER_POSTGRES_PASSWORD")
DAGSTER_POSTGRES_PORT = config.require("DAGSTER_POSTGRES_PORT")
IMAGE_TAG = config.require("IMAGE_TAG")
IMAGE_NAME_USER_CODE = config.require("IMAGE_NAME_USER_CODE")
IMAGE_NAME_DAEMON = config.require("IMAGE_NAME_DAEMON")
IMAGE_NAME_WEB_SERVER = config.require("IMAGE_NAME_WEB_SERVER")
# If not using Assigned Identities to pull/push images, this is not necesary
SUBSCRIPTION_ID = config.require("SUBSCRIPTION_ID")
USER_CODE_PORT = config.require("USER_CODE_PORT")

rg_random_suffix = RandomString("rgRandomSuffix", length=8, special=False, upper=False).result
resource_group_name = pulumi.Output.all(DAGSTER_RG, rg_random_suffix).apply(lambda args: f"{args[0]}-{args[1]}")

resource_group = resources.ResourceGroup(
    "dagsterResourceGroup",
    resource_group_name=resource_group_name,
    location="eastus"
)

pg_random_suffix = RandomString("pgRandomSuffix", length=8, special=False, upper=False).result
pg_cluster_name = pulumi.Output.all("burstablev1", pg_random_suffix).apply(lambda args: f"{args[0]}{args[1]}")
single_node_pg_cluster = dbforpostgresql.Cluster(
    "clusterSingleNode",
    cluster_name=pg_cluster_name,
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
    tags={"Environment": ENV})

firewall_rule = dbforpostgresql.v20221108.FirewallRule(
    "firewallRule",
    firewall_rule_name="rule1",
    cluster_name=single_node_pg_cluster.name,
    resource_group_name=resource_group.name,
    start_ip_address="0.0.0.0",
    end_ip_address="255.255.255.255",
    opts=pulumi.ResourceOptions(depends_on=[single_node_pg_cluster]))

container_env_logs = operationalinsights.Workspace("workspace",
    workspace_name="acctest-01",
    location=resource_group.location,
    resource_group_name=resource_group.name,
    sku={"name": operationalinsights.WorkspaceSkuNameEnum.PER_GB2018},
    retention_in_days=30,
    tags={"Environment": ENV})

log_shared_keys_o = operationalinsights.get_workspace_shared_keys_output(
    resource_group_name=resource_group.name,
    workspace_name=container_env_logs.name)

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
    zone_redundant=False,
    tags={"Environment": ENV})

acr_random_suffix = RandomString("acrRandomSuffix", length=2, special=False,upper=False).result
acr_name = pulumi.Output.all(ACR_NAME, acr_random_suffix).apply(lambda args: f"{args[0]}{args[1]}")
acr = containerregistry.Registry(
    "acr",
    registry_name=acr_name,
    resource_group_name=resource_group.name,
    location=resource_group.location,
    sku=containerregistry.SkuArgs(name="Basic"),
    admin_user_enabled=True,
    opts=pulumi.ResourceOptions(parent=resource_group),
    tags={"Environment": ENV})

# A push role can be used to avoid using admin user
acr_credentials = containerregistry.list_registry_credentials_output(
    resource_group_name=resource_group.name,
    registry_name=acr.name)

acr_username = acr_credentials.username
acr_password = acr_credentials.passwords[0].value

user_code_image = Image(
    "userCodeImage",
    build=DockerBuildArgs(
        context="../dags",
        dockerfile="../dags/Dockerfile_user_code",
        platform="linux/amd64"
    ),
    image_name=acr.login_server.apply(lambda r: f"{r}/{IMAGE_NAME_USER_CODE}:{IMAGE_TAG}"),
    registry={
        "server": acr.login_server,
        "username": acr_username,
        "password": acr_password,
    })

dagster_image = Image(
    "dagsterImage",
    build=DockerBuildArgs(
        context="../dagster-backend",
        dockerfile="../dagster-backend/Dockerfile_dagster",
        platform="linux/amd64"
    ),
    image_name=acr.login_server.apply(lambda r: f"{r}/{IMAGE_NAME_DAEMON}:{IMAGE_TAG}"),
    registry={
        "server": acr.login_server,
        "username": acr_username,
        "password": acr_password,
    }
)

acr_o = pulumi.Output.from_input(acr)



## Container Apps - User Code
USER_CODE_APP_NAME = "usercode"
user_code_app = app.ContainerApp(
    "userCodeApp",
    container_app_name=USER_CODE_APP_NAME,
    location=resource_group.location,
    resource_group_name=resource_group.name,
    environment_id=container_env.id,
    configuration=app.ConfigurationArgs(
        ingress=app.IngressArgs(
            external=False,
            transport= app.IngressTransportMethod.TCP,
            exposed_port=4000,
            target_port=4000,
            allow_insecure=False
        ),
        secrets=[app.SecretArgs(
            name="acr-password",
            value=acr_password
        )],
        registries=[
            app.RegistryCredentialsArgs(
                username=acr_username, 
                password_secret_ref="acr-password",
                server=acr_o.apply(lambda x: x.login_server)
            )]
        # Identity
        # registries=[
        #     app.RegistryCredentialsArgs(
        #         identity=container_app_identity.id,
        #         server=acr_o.apply(lambda x: x.login_server)
        #     )]
    ),
    template=app.TemplateArgs(
        containers=[app.ContainerArgs(
            image=user_code_image.image_name,
            name=USER_CODE_APP_NAME,
            env=[
                app.EnvironmentVarArgs(
                    name="FORCE_REDEPLOY",
                    value=user_code_image.repo_digest  # Triggers redeploy only when image changes
                )
            ],
            resources=app.ContainerResourcesArgs(
                cpu=0.75,
                memory="1.5Gi"
            )
        )]
    ),
    tags={"Environment": ENV})

# Update environment variable definitions to handle Output types
DAGSTER_POSTGRES_HOST = single_node_pg_cluster.server_names.apply(
    lambda names: names[0].fully_qualified_domain_name
)
DAGSTER_POSTGRES_USER = "citus"
DAGSTER_POSTGRES_DB = "citus"
USER_CODE_HOST = "usercode"
# USER_CODE_HOST = user_code_app.configuration.apply(lambda config: config.ingress.fqdn)

def make_container_env_vars(postgres_host, postgres_port, user_code_port, postgres_password, run_type):
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
        ),
        app.EnvironmentVarArgs(
            name="RUN_TYPE",
            value=run_type
        )
    ]

# Update container app templates to use all Output parameters
def get_container_env_vars(run_type: str):
    return pulumi.Output.all(
        DAGSTER_POSTGRES_HOST,
        DAGSTER_POSTGRES_PORT,
        USER_CODE_PORT,
        DAGSTER_POSTGRES_PASSWORD,
        run_type
    ).apply(lambda args: make_container_env_vars(*args))

## Container Apps - Daemon
DAEMON_APP_NAME = "daemon"
daemon_app = app.ContainerApp(
    "daemonApp",
    container_app_name=DAEMON_APP_NAME,
    location=resource_group.location,
    resource_group_name=resource_group.name,
    environment_id=container_env.id,
    # identity=app.ManagedServiceIdentityArgs(
    #     type=app.ManagedServiceIdentityType.USER_ASSIGNED,
    #     user_assigned_identities=[container_app_identity.id]
    # ),
    configuration=app.ConfigurationArgs(
        secrets=[app.SecretArgs(
            name="acr-password",
            value=acr_password
        )],
        registries=[
            app.RegistryCredentialsArgs(
                username=acr_username, 
                password_secret_ref="acr-password",
                server=acr_o.apply(lambda x: x.login_server)
            )]
        # Identity
        # registries=[
        #     app.RegistryCredentialsArgs(
        #         identity=container_app_identity.id,
        #         server=acr_o.apply(lambda x: x.login_server)
        #     )]
    ),
    template=app.TemplateArgs(
        containers=[app.ContainerArgs(
            image=dagster_image.image_name,
            name=DAEMON_APP_NAME,
            env=get_container_env_vars("DAEMON"),
            resources=app.ContainerResourcesArgs(
                cpu=0.75,
                memory="1.5Gi"
            )
        )]
    ))

## Container Apps - Web Server
WEB_SERVER_APP_NAME = "webserver"
web_server_app = app.ContainerApp(
    "webServer",
    container_app_name=WEB_SERVER_APP_NAME,
    location=resource_group.location,
    resource_group_name=resource_group.name,
    environment_id=container_env.id,
    # identity=app.ManagedServiceIdentityArgs(
    #     type=app.ManagedServiceIdentityType.USER_ASSIGNED,
    #     user_assigned_identities=[container_app_identity.id]
    # ),
    configuration=app.ConfigurationArgs(
        ingress=app.IngressArgs(
            external=True,
            transport= app.IngressTransportMethod.HTTP,
            target_port=3000,
            allow_insecure=False
        ),
        secrets=[app.SecretArgs(
            name="acr-password",
            value=acr_password
        )],
        registries=[
            app.RegistryCredentialsArgs(
                username=acr_username, 
                password_secret_ref="acr-password",
                server=acr_o.apply(lambda x: x.login_server)
            )]
        # Identity
        # registries=[
        #     app.RegistryCredentialsArgs(
        #         identity=container_app_identity.id,
        #         server=acr_o.apply(lambda x: x.login_server)
        #     )]
    ),
    template=app.TemplateArgs(
        containers=[app.ContainerArgs(
            image=dagster_image.image_name,
            name=WEB_SERVER_APP_NAME,
            env=get_container_env_vars("WEBSERVER"),
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

# # Identity
# pulumi.export("containerAppIdentityId", container_app_identity.id)
# pulumi.export("containerAppIdentityPrincipalId", container_app_identity.principal_id)
# pulumi.export("containerAppIdentityClientId", container_app_identity.client_id)

# Container Apps
pulumi.export("userCodeAppId", user_code_app.id)
pulumi.export("userCodeAppName", user_code_app.name)
pulumi.export("userCodeAppUrl", 
    user_code_app.configuration.apply(lambda config: config.ingress.fqdn if config.ingress else None))

pulumi.export("daemonAppId", daemon_app.id)
pulumi.export("daemonAppName", daemon_app.name)

pulumi.export("webServerAppId", web_server_app.id)
pulumi.export("webServerAppName", web_server_app.name)
pulumi.export(
    "webServerPublicUrl", 
    web_server_app.configuration.apply(lambda config: config.ingress.fqdn))

# Role Assignment
# pulumi.export("acrPullRoleAssignmentId", acr_pull_assignment.id)
