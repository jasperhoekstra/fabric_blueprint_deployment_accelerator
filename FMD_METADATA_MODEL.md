---
Title: FMD Data Model reference
Description: Learn about the metadata tables and schema used by the Fabric Metadata-Driven (FMD) Framework.
Topic: reference
Date: 07/2025
Author: edkreuk
---

# FMD Data Model reference

This article describes the metadata tables and schema used by the Fabric Metadata-Driven (FMD) Framework. The data model enables dynamic orchestration, lineage, and governance across your data platform.

![FMD Metadata Overview](/Images/FMD_METADATA_OVERVIEW.png)

## Integration schema

The integration schema contains core metadata tables for connections, data sources, workspaces, pipelines, and lakehouses.

### Connection

Stores all connection definitions.

| Column           | Data type        | Constraints                    | Description                                 |
|------------------|-----------------|--------------------------------|---------------------------------------------|
| ConnectionId     | int             | PRIMARY KEY, IDENTITY(1,1)     | Unique identifier for the connection        |
| ConnectionGuid   | uniqueidentifier| UNIQUE                         | GUID of the connection in Fabric            |
| Name             | varchar(200)    | NOT NULL                       | Name of the connection                      |
| Type             | varchar(50)     | NOT NULL                       | Type of the connection                      |
| GatewayType      | varchar(50)     | NULL                           | Type of gateway used, if applicable         |
| DatasourceReference | varchar(max) | NULL                           | Reference to the data source                |
| IsActive         | bit             | NOT NULL, DEFAULT ((1))        | Indicates if the connection is active       |

### DataSource

Stores all data sources. Each data source is associated with a connection.

| Column           | Data type        | Constraints                    | Description                                 |
|------------------|-----------------|--------------------------------|---------------------------------------------|
| DataSourceId     | int             | PRIMARY KEY, IDENTITY(1,1)     | Unique identifier for the data source       |
| ConnectionId     | int             | NOT NULL                       | Reference to the associated connection      |
| Name             | varchar(100)    | NOT NULL                       | Name of the data source (e.g., database)    |
| Namespace        | varchar(100)    | NOT NULL                       | Prefix for the table in the lakehouse       |
| Type             | varchar(30)     | NULL                           | Type of data source (for pipeline selection)|
| Description      | nvarchar(200)   | NULL                           | Description of the data source              |
| IsActive         | bit             | NOT NULL, DEFAULT ((1))        | Indicates if the data source is active      |

#### Connection types

| Connection         | Type         |
|--------------------|-------------|
| SQL Connection     | ASQL_01, ASQL_02 |
| Datalake           | ADLS_01     |
| Azure Data Factory | ADF         |

### Workspace

Stores workspace metadata. Workspaces are added by default during setup.

| Column         | Data type        | Constraints                    | Description                                 |
|----------------|-----------------|--------------------------------|---------------------------------------------|
| WorkspaceId    | int             | PRIMARY KEY, IDENTITY(1,1)     | Unique identifier for workspace             |
| WorkspaceGuid  | uniqueidentifier| UNIQUE                         | Workspace GUID from Fabric                  |
| Name           | varchar(100)    | NOT NULL                       | Name of the workspace                       |

### Pipeline

Stores pipeline metadata per workspace. Populated during setup.

| Column         | Data type        | Constraints                    | Description                                 |
|----------------|-----------------|--------------------------------|---------------------------------------------|
| PipelineId     | int             | PRIMARY KEY, IDENTITY(1,1)     | Unique identifier for pipeline              |
| PipelineGuid   | uniqueidentifier| UNIQUE                         | Pipeline GUID from Fabric                   |
| WorkspaceGuid  | uniqueidentifier| NOT NULL                       | Reference to the workspace                  |
| Name           | varchar(200)    | NOT NULL                       | Name of the pipeline                        |
| IsActive       | bit             | NOT NULL, DEFAULT ((1))        | Indicates if the pipeline is active         |

### Lakehouse

Stores lakehouse metadata. Populated during setup.

| Column         | Data type        | Constraints                    | Description                                 |
|----------------|-----------------|--------------------------------|---------------------------------------------|
| LakehouseId    | int             | PRIMARY KEY, IDENTITY(1,1)     | Unique identifier for lakehouse             |
| LakehouseGuid  | uniqueidentifier| UNIQUE                         | Lakehouse GUID from Fabric                  |
| WorkspaceGuid  | uniqueidentifier| NOT NULL                       | Reference to the workspace                  |
| Name           | varchar(100)    | NOT NULL                       | Name of the lakehouse                       |
| IsActive       | bit             | NOT NULL, DEFAULT ((1))        | Indicates if the lakehouse is active        |

## Entity tables

These tables define the entities managed in each layer of the medallion architecture.

### LandingzoneEntity

Stores metadata for landing zone entities.

| Column                | Data type        | Constraints                    | Description                                 |
|-----------------------|-----------------|--------------------------------|---------------------------------------------|
| LandingzoneEntityId   | bigint          | PRIMARY KEY, IDENTITY(1,1)     | Unique identifier for the landing zone entity|
| DataSourceId          | int             | NOT NULL                       | Reference to the data source                |
| LakehouseId           | int             | NOT NULL                       | Reference to the lakehouse                  |
| SourceSchema          | nvarchar(100)   | NULL                           | Schema of the source table or file folder   |
| SourceName            | nvarchar(200)   | NOT NULL                       | Name of the source table or file            |
| SourceCustomSelect    | nvarchar(4000)  | NULL                           | Optional custom select value                |
| FileName              | nvarchar(200)   | NOT NULL                       | File name in the landing zone               |
| FileType              | nvarchar(20)    | NOT NULL                       | File type (e.g., csv, parquet)              |
| FilePath              | nvarchar(500)   | NOT NULL                       | Folder path in the lakehouse                |
| IsIncremental         | bit             | NOT NULL, DEFAULT ((0))        | Indicates if incremental loading is enabled |
| IsIncrementalColumn   | nvarchar(50)    | NULL                           | Column used for incremental loading         |
| IsActive              | bit             | NOT NULL, DEFAULT ((1))        | Indicates if the entity is active           |

![LandingzoneEntity](/Images/FMD_LandingzoneEntity.png)

### BronzeLayerEntity

Stores metadata for bronze layer entities.

| Column                | Data type        | Constraints                    | Description                                 |
|-----------------------|-----------------|--------------------------------|---------------------------------------------|
| BronzeLayerEntityId   | bigint          | PRIMARY KEY, IDENTITY(1,1)     | Unique identifier for the bronze entity     |
| LandingzoneEntityId   | bigint          | NOT NULL                       | Reference to the landing zone entity        |
| LakehouseId           | int             | NOT NULL                       | Reference to the lakehouse                  |
| Schema                | nvarchar(100)   | NOT NULL                       | Schema in the bronze layer                  |
| Name                  | nvarchar(200)   | NOT NULL                       | Name of the table                           |
| PrimaryKeys           | nvarchar(200)   | NOT NULL                       | Primary keys for the table                  |
| FileType              | nvarchar(20)    | NOT NULL, DEFAULT ('Delta')    | File type (e.g., Delta)                     |
| CleansingRules        | nvarchar(max)   | NULL                           | Cleansing rules to be applied               |
| IsActive              | bit             | NOT NULL, DEFAULT ((1))        | Indicates if the entity is active           |

![BronzeLayerEntity](/Images/FMD_BronzeLayerEntity.png)

### SilverLayerEntity

Stores metadata for silver layer entities.

| Column                | Data type        | Constraints                    | Description                                 |
|-----------------------|-----------------|--------------------------------|---------------------------------------------|
| SilverLayerEntityId   | bigint          | PRIMARY KEY, IDENTITY(1,1)     | Unique identifier for the silver entity     |
| BronzeLayerEntityId   | bigint          | NOT NULL                       | Reference to the bronze layer entity        |
| LakehouseId           | int             | NOT NULL                       | Reference to the lakehouse                  |
| Schema                | nvarchar(100)   | NULL                           | Schema in the silver layer                  |
| Name                  | nvarchar(200)   | NULL                           | Name of the table                           |
| FileType              | nvarchar(20)    | NOT NULL, DEFAULT ('Delta')    | File type (e.g., Delta)                     |
| CleansingRules        | nvarchar(max)   | NULL                           | Cleansing rules to be applied               |
| IsActive              | bit             | NOT NULL, DEFAULT ((1))        | Indicates if the entity is active           |

![SilverLayerEntity](/Images/FMD_SilverLayerEntity.png)

### Domain

Represents a bounded context in the deployment accelerator. Domains are mastered inside the Fabric SQL orchestration database and provide governance defaults, sensitivity tags, and retention policies that can be inherited by individual layers and entities. The deployment script (`setup/fabric_blueprint_deployer.py`) reads these tables to generate environment manifests.

| Column              | Data type      | Constraints                                   | Description                                                  |
|---------------------|----------------|-----------------------------------------------|--------------------------------------------------------------|
| DomainId            | int            | PRIMARY KEY, IDENTITY(1,1)                    | Surrogate identifier for the domain                          |
| Name                | varchar(100)   | UNIQUE, NOT NULL                              | Canonical domain name (used in configuration overlays)       |
| Code                | varchar(50)    | UNIQUE, NOT NULL                              | Short code used for workspace naming                         |
| DisplayName         | nvarchar(200)  | NOT NULL                                     | Friendly domain name displayed in automation outputs         |
| Description         | nvarchar(400)  | NULL                                          | Optional description                                         |
| Owner               | nvarchar(200)  | NULL                                          | Domain owner or group                                        |
| Classification      | varchar(50)    | NULL                                          | Security classification                                      |
| SensitivityTag      | varchar(100)   | NULL                                          | Optional sensitivity or Purview tag                          |
| HasSensitiveData    | bit            | NOT NULL, DEFAULT ((0))                       | Indicates if the domain contains sensitive data              |
| RetentionPolicy     | varchar(50)    | NULL                                          | High-level retention policy (bronze/silver/gold/etc.)        |
| RetentionDays       | int            | NULL                                          | Recommended retention duration in days                       |
| DataQualityRuleset  | varchar(100)   | NULL                                          | Default ruleset applied to entities in the domain            |
| Tags                | nvarchar(400)  | NULL                                          | Additional metadata tags                                     |
| IsActive            | bit            | NOT NULL, DEFAULT ((1))                       | Indicates whether the domain is active                       |

### DomainLayer

Stores the mapping between a domain and each logical layer (raw, consolidated, curated, optional domain layers). This table enables per-layer governance and workspace assignments.

| Column           | Data type      | Constraints                                   | Description                                                  |
|------------------|----------------|-----------------------------------------------|--------------------------------------------------------------|
| DomainLayerId    | int            | PRIMARY KEY, IDENTITY(1,1)                    | Surrogate identifier                                         |
| DomainId         | int            | FOREIGN KEY REFERENCES Domain(DomainId)       | Associated domain                                            |
| LayerKey         | varchar(50)    | NOT NULL                                      | Layer identifier (e.g., raw, curated, playground)            |
| LayerCode        | varchar(100)   | NOT NULL                                      | Workspace naming code (e.g., 1000_RAW)                       |
| WorkspaceRole    | varchar(50)    | NOT NULL                                      | Role of the workspace (landing, silver, gold, analytics)     |
| IsRequired       | bit            | NOT NULL, DEFAULT ((0))                       | Indicates if the layer is mandatory for the domain           |
| IsActive         | bit            | NOT NULL, DEFAULT ((1))                       | Indicates if the mapping is active                           |

### DomainWorkspace

Captures the environment-specific workspace GUIDs for each domain and layer combination, enabling the DTAP deployment automation to target the correct Fabric workspace.

| Column            | Data type        | Constraints                                             | Description                                                  |
|-------------------|------------------|---------------------------------------------------------|--------------------------------------------------------------|
| DomainWorkspaceId | int              | PRIMARY KEY, IDENTITY(1,1)                              | Surrogate identifier                                         |
| DomainLayerId     | int              | FOREIGN KEY REFERENCES DomainLayer(DomainLayerId)       | Associated domain-layer mapping                              |
| EnvironmentName   | varchar(50)      | NOT NULL                                               | Environment name (dev, test, acc, prod, etc.)                |
| WorkspaceGuid     | uniqueidentifier | NOT NULL                                               | GUID of the Fabric workspace                                 |
| WorkspaceName     | nvarchar(200)    | NOT NULL                                               | Friendly workspace name                                      |
| CiCdStage         | varchar(50)      | NULL                                                   | Stage identifier used by CI/CD pipeline                      |
| DeploymentMode    | varchar(20)      | NULL                                                   | Deployment mode (incremental, complete, safe)                |
| IsActive          | bit              | NOT NULL, DEFAULT ((1))                                | Indicates if the workspace record is active                  |

### DomainEntity

Links orchestration entities (landing, bronze, silver, curated, etc.) to the domain layer and includes governance tags and quality rulesets specific to each entity.

| Column         | Data type      | Constraints                                             | Description                                                  |
|----------------|----------------|---------------------------------------------------------|--------------------------------------------------------------|
| DomainEntityId | int            | PRIMARY KEY, IDENTITY(1,1)                              | Surrogate identifier                                         |
| DomainLayerId  | int            | FOREIGN KEY REFERENCES DomainLayer(DomainLayerId)       | Associated domain-layer mapping                              |
| EntityType     | varchar(50)    | NOT NULL                                               | Type of entity (Landingzone, Bronze, Silver, Semantic, etc.) |
| EntityId       | int            | NOT NULL                                               | Identifier of the entity in the corresponding table          |
| GovernanceTags | nvarchar(400)  | NULL                                                   | Applied governance tags                                      |
| QualityRuleset | varchar(100)   | NULL                                                   | Data quality ruleset applied during orchestration            |
| IsActive       | bit            | NOT NULL, DEFAULT ((1))                                | Indicates if the entity association is active                |

### DomainTable

Captures table-level governance metadata for every domain layer, allowing retention, classification, and sensitivity controls to be applied per table and per environment.

| Column            | Data type        | Constraints                                             | Description                                               |
|-------------------|------------------|---------------------------------------------------------|-----------------------------------------------------------|
| DomainTableId     | int              | PRIMARY KEY, IDENTITY(1,1)                              | Surrogate identifier                                      |
| DomainLayerId     | int              | FOREIGN KEY REFERENCES DomainLayer(DomainLayerId)       | Associated domain-layer mapping                           |
| EnvironmentName   | varchar(50)      | NULL                                                   | Optional environment override (NULL applies to all)       |
| SchemaName        | nvarchar(128)    | NOT NULL                                               | Delta table schema name                                   |
| TableName         | nvarchar(128)    | NOT NULL                                               | Delta table name                                          |
| DisplayName       | nvarchar(200)    | NULL                                                   | Friendly display name for documentation                   |
| Description       | nvarchar(400)    | NULL                                                   | Additional table description                              |
| Classification    | varchar(50)      | NULL                                                   | Sensitivity classification applied to the table           |
| SensitivityTag    | nvarchar(100)    | NULL                                                   | Purview/Microsoft Information Protection tag              |
| HasSensitiveData  | bit              | NULL                                                   | Overrides the domain-level sensitive data flag            |
| RetentionPolicy   | varchar(100)     | NULL                                                   | Retention policy override                                 |
| RetentionDays     | int              | NULL                                                   | Retention duration override in days                       |
| DataQualityRuleset| varchar(100)     | NULL                                                   | Data-quality ruleset applied to the table                 |
| Tags              | nvarchar(400)    | NULL                                                   | Additional metadata tags applied to the table             |
| IsActive          | bit              | NOT NULL, DEFAULT ((1))                                | Indicates if the table metadata row is active             |

### SemanticModel

Stores semantic model metadata aligned to each domain layer, including dataset names, refresh pipelines, and sensitivity information.

| Column          | Data type      | Constraints                                             | Description                                                  |
|-----------------|----------------|---------------------------------------------------------|--------------------------------------------------------------|
| SemanticModelId | int            | PRIMARY KEY, IDENTITY(1,1)                              | Surrogate identifier                                         |
| DomainLayerId   | int            | FOREIGN KEY REFERENCES DomainLayer(DomainLayerId)       | Associated domain-layer mapping                              |
| ModelName       | nvarchar(200)  | NOT NULL                                               | Semantic model name                                          |
| DatasetName     | nvarchar(200)  | NOT NULL                                               | Power BI dataset name                                        |
| WorkspaceLayer  | varchar(50)    | NOT NULL                                               | Layer where the semantic model resides (curated, analytics)  |
| RefreshPipeline | nvarchar(200)  | NULL                                                   | Pipeline used to refresh the semantic model                  |
| Tags            | nvarchar(400)  | NULL                                                   | Additional tags applied to the semantic model                |
| Classification  | varchar(50)    | NULL                                                   | Sensitivity classification                                   |
| HasSensitiveData| bit            | NOT NULL, DEFAULT ((0))                                | Indicates if the semantic model contains sensitive data      |
| RetentionDays   | int            | NULL                                                   | Retention duration for audit history                         |
| IsActive        | bit            | NOT NULL, DEFAULT ((1))                                | Indicates if the semantic model is active                    |

### SemanticLink

Captures relationships between semantic models and their source entities across domains and layers. Used to publish semantic links and lineage to the Fabric CI/CD tooling.

| Column              | Data type        | Constraints                                             | Description                                                  |
|---------------------|------------------|---------------------------------------------------------|--------------------------------------------------------------|
| SemanticLinkId      | int              | PRIMARY KEY, IDENTITY(1,1)                              | Surrogate identifier                                         |
| SemanticModelId     | int              | FOREIGN KEY REFERENCES SemanticModel(SemanticModelId)   | Associated semantic model                                    |
| SourceDomainLayerId | int              | FOREIGN KEY REFERENCES DomainLayer(DomainLayerId)       | Source domain layer                                          |
| SourceEntityType    | varchar(50)      | NOT NULL                                               | Type of the source entity                                    |
| SourceEntityId      | int              | NOT NULL                                               | Identifier of the source entity                              |
| LinkType            | varchar(50)      | NOT NULL                                               | Link type (e.g., relationship, measure)                      |
| Relationship        | nvarchar(200)    | NULL                                                   | Relationship name or description                             |
| Measures            | nvarchar(max)    | NULL                                                   | JSON payload of measures or calculations                     |
| IsActive            | bit              | NOT NULL, DEFAULT ((1))                                | Indicates if the link is active                              |

The following stored procedures support the new domain-aware blueprint:

- `[integration].[sp_UpsertDomain]`, `[integration].[sp_UpsertDomainLayer]`, `[integration].[sp_UpsertDomainWorkspace]`, `[integration].[sp_UpsertSemanticModel]`, `[integration].[sp_UpsertDomainEntity]`, `[integration].[sp_UpsertDomainTable]`, and `[integration].[sp_UpsertSemanticLink]` manage inserts and updates from the deployment configuration and setup automation. When the deployer is executed with the `--seed` flag it will call these stored procedures using the `seedDomains` section of `config/blueprint.yaml`.
- `[execution].[sp_GetDomainLayerEntities]`, `[execution].[sp_GetDomainTables]`, and `[execution].[sp_GetSemanticLinks]` expose environment-aware manifests for pipelines and notebooks, enabling orchestration assets to retrieve only the entities, table governance metadata, and semantic definitions relevant to the selected domain/layer.

### Deployment automation

`setup/fabric_blueprint_deployer.py` orchestrates the full deployment-as-code workflow:

1. Reads `config/blueprint.yaml` for SQL connection settings, DTAP environment metadata, and layer templates.
2. Applies the SQL package defined in `config/sql_deployment.json` (when invoked with `--apply-sql`), ensuring the orchestration database schema is present.
3. Optionally seeds domain metadata into the database (`--seed`) so that subsequent runs can be fully driven from SQL.
4. Queries the orchestration tables to generate environment-specific manifests and governance scaffolding under `environments/`.

Because the SQL database is now the single source of truth for domains and layers, adding, updating, or removing a domain only requires running the deployer after modifying the metadata (either through stored procedures or pipeline-driven automation).

