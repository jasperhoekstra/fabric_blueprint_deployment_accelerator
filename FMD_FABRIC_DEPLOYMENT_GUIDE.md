# Fabric Deployment Accelerator — Runbook

This guide explains how to run the deployment accelerator entirely from Microsoft Fabric using the assets in this repository. It assumes that the source code is stored in Azure DevOps and synchronised with your Fabric workspaces.

## 1. Provision the management workspaces

1. **Create a Fabric workspace named `0000_deployment accelerator`.**
   - Connect the workspace to your Azure DevOps repository so the `/config`, `/setup`, and `/src` folders are available under **Files**.
   - Create or reuse a Lakehouse (for example `0000_DEPLOYMENT_FILES`) so the repository contents and manifests can live under `Files/`.

2. **Create a Fabric workspace named `0000 [ Company ] Dataplatform Management & Orchestration`.**
   - Add a SQL database item (Data Warehouse) named `FabricOrchestration`.
   - Grant the service principal or user that will run the deployment notebook the `dbo` role on this SQL database.

The SQL workspace becomes the system of record for domains, layers, workspaces, and table-level governance. The deployment notebook runs from the accelerator workspace and connects to the orchestration SQL database.

## 2. Prepare the configuration file

1. Update `config/blueprint.yaml` with your SQL connection details. The notebook expects the file to be reachable at `Files/fabric_blueprint_deployment_accelerator/config/blueprint.yaml` inside the accelerator workspace. The connection string must point to the `FabricOrchestration` database inside the orchestration workspace.
2. Optionally add entries to `seedDomains` if you want the first run to populate example domains. Table-level metadata can be provided by adding items under `tables` for each domain seed (see the inline comments for the structure).
3. Commit and push the configuration change to Azure DevOps so the workspace sync picks it up.

## 3. Run the Fabric notebook

1. In the accelerator workspace open the notebook `setup/NB_FABRIC_BLUEPRINT_DEPLOYMENT.ipynb`.
2. In **Section 1** set `REPO_ROOT` if your repository is stored in a different folder. Toggle `APPLY_SQL`, `SEED_DOMAINS`, and `TARGET_ENVIRONMENTS` depending on whether you are setting up the orchestration database or only refreshing manifests.
3. Execute Section 2 the first time per session to install dependencies (`pyyaml` and `pyodbc`).
4. Execute Section 3 to run the deployer. When `APPLY_SQL=True` the notebook applies `config/sql_deployment.json`, creating or updating all schemas, including the new table-level governance metadata. The same run generates manifests and governance files under `environments/<env>/` in the repository.
5. Use Section 4 (`preview_manifest`) to confirm the generated output.

The notebook is designed to run inside Fabric, so no external CLI or pipeline is required. If you prefer automation, create a Fabric pipeline that invokes the notebook using the template under `src/PL_FABRIC_BLUEPRINT_DEPLOY.DataPipeline` and replace the placeholder workspace and notebook identifiers with your own.

## 4. Manage domains and table governance from SQL

The SQL deployment package creates procedures that let you define domains, layers, workspaces, semantic models, and table-level governance without editing the config file. Key procedures:

- `integration.sp_UpsertDomain` — registers or updates a domain.
- `integration.sp_UpsertDomainLayer` — enables a layer for a domain (raw, consolidated, curated, or optional domains).
- `integration.sp_UpsertDomainWorkspace` — maps a domain layer to a Fabric workspace per environment (Dev/Test/Acc/Prod).
- `integration.sp_UpsertDomainTable` — records table-level governance for a domain layer, including classification, retention, and PII flags.
- `integration.sp_UpsertSemanticModel` and `integration.sp_UpsertSemanticLink` — manage curated semantic metadata.

Use the orchestration SQL database as the source of truth:

```sql
EXEC integration.sp_UpsertDomain @DomainName = 'finance', @Code = 'FIN', @DisplayName = 'Finance';
EXEC integration.sp_UpsertDomainLayer @DomainName = 'finance', @LayerKey = 'raw', @LayerCode = '1000_RAW', @WorkspaceRole = 'landing', @IsRequired = 1;
EXEC integration.sp_UpsertDomainWorkspace @DomainName = 'finance', @LayerKey = 'raw', @EnvironmentName = 'dev',
    @WorkspaceGuid = 'GUID-FOR-DEV-RAW', @WorkspaceName = 'DEV_1000_RAW_FINANCE';
EXEC integration.sp_UpsertDomainTable @DomainName = 'finance', @LayerKey = 'curated', @SchemaName = 'curated',
    @TableName = 'fact_sales', @Classification = 'Confidential', @SensitivityTag = 'PII',
    @HasSensitiveData = 1, @RetentionPolicy = 'regulatory', @RetentionDays = 1825, @Tags = 'sales,gold';
```

After updating metadata, re-run the notebook (or pipeline) to regenerate manifests and governance files.

## 5. Using the generated assets

- Generated manifests and governance files land under `environments/<environment>/<domain>_<layer>/`. The `governance.yaml` contains layer-level controls while `tables.yaml` lists table-specific policies.
- Use these outputs to drive Fabric CI/CD tooling or documentation processes, or to feed additional notebooks/pipelines in downstream workspaces.
- Because the repository excludes generated manifests via `.gitignore`, download the required artifacts from the workspace or package them as part of your release pipelines.

## 6. Adding or removing domains later

To add a new domain, call the `integration.sp_UpsertDomain*` procedures for the domain and its layers/workspaces, then re-run the notebook. To retire a domain or layer, set `@IsActive = 0` when calling the appropriate stored procedure. The manifest generator automatically filters inactive entries.

## 7. Governance checks

- Table-level governance is stored in `integration.DomainTable` and surfaced in manifests and `tables.yaml`.
- Use `execution.sp_GetDomainTables` to validate governance metadata that will be applied during deployments:

```sql
EXEC execution.sp_GetDomainTables @DomainName = 'finance', @LayerKey = 'curated', @EnvironmentName = 'prod';
```

Review the output before promoting changes to Test/Acc/Prod.

With this setup the accelerator remains fully managed inside Fabric—domains, workspaces, and governance live in SQL, the deployment notebook runs inside the accelerator workspace, and pipelines act only as orchestrators for notebooks.
