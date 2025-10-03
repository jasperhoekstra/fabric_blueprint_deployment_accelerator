#!/usr/bin/env python3
"""Deploy the Fabric domain blueprint from a single configuration file."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

LOGGER = logging.getLogger("fabric_blueprint_deployer")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "blueprint.yaml"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "environments"
DEFAULT_PACKAGE_PATH = REPO_ROOT / "config" / "sql_deployment.json"


class BlueprintError(RuntimeError):
    """Generic error for blueprint operations."""


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise BlueprintError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_json(path: Path) -> Any:
    if not path.exists():
        raise BlueprintError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@dataclass
class LayerTemplate:
    key: str
    code: str
    workspace_role: str
    description: Optional[str] = None
    governance: Dict[str, Any] = field(default_factory=dict)
    artifact_defaults: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DomainLayerWorkspace:
    environment: str
    workspace_guid: str
    workspace_name: str
    cicd_stage: Optional[str] = None
    deployment_mode: Optional[str] = None


@dataclass
class DomainSemanticModel:
    name: str
    dataset_name: str
    layer_key: str
    refresh_pipeline: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    classification: Optional[str] = None
    has_sensitive_data: Optional[bool] = None
    retention_days: Optional[int] = None


@dataclass
class DomainTable:
    schema_name: str
    table_name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    environment: Optional[str] = None
    classification: Optional[str] = None
    sensitivity_tag: Optional[str] = None
    has_sensitive_data: Optional[bool] = None
    retention_policy: Optional[str] = None
    retention_days: Optional[int] = None
    data_quality_ruleset: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class DomainLayerData:
    layer_key: str
    layer_code: str
    workspace_role: str
    required: bool
    workspaces: Dict[str, DomainLayerWorkspace] = field(default_factory=dict)
    semantic_models: List[DomainSemanticModel] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[DomainTable] = field(default_factory=list)
    active: bool = True


@dataclass
class DomainData:
    name: str
    code: str
    display_name: str
    description: Optional[str]
    owner: Optional[str]
    classification: Optional[str]
    sensitivity_tag: Optional[str]
    has_sensitive_data: Optional[bool]
    retention_policy: Optional[str]
    retention_days: Optional[int]
    data_quality_ruleset: Optional[str]
    tags: List[str] = field(default_factory=list)
    layers: Dict[str, DomainLayerData] = field(default_factory=dict)


class OfflineDataSource:
    """Create domain metadata from the seed payload in the configuration."""

    def __init__(self, config: Mapping[str, Any], layer_templates: Mapping[str, LayerTemplate]):
        self._config = config
        self._layer_templates = layer_templates

    def fetch_domains(self) -> List[DomainData]:
        seeds = self._config.get("seedDomains", []) or []
        domains: List[DomainData] = []
        for entry in seeds:
            domain = DomainData(
                name=entry["name"],
                code=entry.get("code", entry["name"]).upper(),
                display_name=entry.get("displayName", entry["name"].title()),
                description=entry.get("description"),
                owner=entry.get("owner"),
                classification=entry.get("classification"),
                sensitivity_tag=entry.get("sensitivityTag"),
                has_sensitive_data=entry.get("hasSensitiveData"),
                retention_policy=(entry.get("retention") or {}).get("policy"),
                retention_days=(entry.get("retention") or {}).get("days"),
                data_quality_ruleset=entry.get("dataQualityRuleset"),
                tags=list(entry.get("tags", []) or []),
            )

            layers_cfg = entry.get("layers", {})
            required_layers = set(layers_cfg.get("required", []))
            optional_layers_cfg = layers_cfg.get("optional", {})

            for layer_key, template in self._layer_templates.items():
                is_required = layer_key in required_layers or template.workspace_role in {"landing", "silver", "gold"}
                if not is_required:
                    layer_override = optional_layers_cfg.get(layer_key, {})
                    enabled = layer_override.get("enabled", False)
                    if not enabled:
                        continue
                layer_data = DomainLayerData(
                    layer_key=layer_key,
                    layer_code=template.code,
                    workspace_role=template.workspace_role,
                    required=is_required,
                )
                domain.layers[layer_key] = layer_data

            for table in entry.get("tables", []) or []:
                layer_key = table.get("layerKey")
                table_name = table.get("name")
                if not layer_key or layer_key not in domain.layers or not table_name:
                    continue
                layer_data = domain.layers[layer_key]
                retention = table.get("retention") or {}
                layer_data.tables.append(
                    DomainTable(
                        schema_name=table.get("schema", "dbo"),
                        table_name=table_name,
                        display_name=table.get("displayName"),
                        description=table.get("description"),
                        environment=table.get("environment"),
                        classification=table.get("classification"),
                        sensitivity_tag=table.get("sensitivityTag"),
                        has_sensitive_data=table.get("hasSensitiveData"),
                        retention_policy=retention.get("policy"),
                        retention_days=retention.get("days"),
                        data_quality_ruleset=table.get("dataQualityRuleset"),
                        tags=parse_tags(table.get("tags", [])),
                    )
                )

            env_map = entry.get("environments", {})
            for env_name, env_layers in env_map.items():
                for layer_key, workspace_payload in (env_layers or {}).items():
                    if layer_key not in domain.layers:
                        continue
                    workspace = DomainLayerWorkspace(
                        environment=env_name,
                        workspace_guid=str(workspace_payload["workspaceGuid"]),
                        workspace_name=workspace_payload["workspaceName"],
                        cicd_stage=workspace_payload.get("ciCdStage"),
                        deployment_mode=workspace_payload.get("deploymentMode"),
                    )
                    domain.layers[layer_key].workspaces[env_name] = workspace

            for semantic in entry.get("semanticModels", []) or []:
                model = DomainSemanticModel(
                    name=semantic["name"],
                    dataset_name=semantic.get("datasetName", semantic["name"]),
                    layer_key=semantic.get("layerKey", semantic.get("workspaceLayer", "curated")),
                    refresh_pipeline=semantic.get("refreshPipeline"),
                    tags=list(semantic.get("tags", []) or []),
                    classification=semantic.get("classification"),
                    has_sensitive_data=semantic.get("hasSensitiveData"),
                    retention_days=semantic.get("retentionDays"),
                )
                if model.layer_key in domain.layers:
                    domain.layers[model.layer_key].semantic_models.append(model)

            for entity in entry.get("entities", []) or []:
                layer_key = entity.get("layerKey")
                if layer_key and layer_key in domain.layers:
                    domain.layers[layer_key].entities.append(entity)

            domains.append(domain)

        return domains


class SqlDataSource:
    """Interact with the Fabric SQL orchestration database."""

    def __init__(self, config: Mapping[str, Any], layer_templates: Mapping[str, LayerTemplate], offline: bool = False):
        self._config = config
        self._layer_templates = layer_templates
        self._offline = offline
        self._connection = None
        self._pyodbc = None
        if not offline:
            try:
                import pyodbc  # type: ignore

                self._pyodbc = pyodbc
            except ImportError as exc:  # pragma: no cover - runtime dependency
                raise BlueprintError(
                    "pyodbc is required for SQL execution. Install it or run with --offline."
                ) from exc

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def _build_connection_string(self, database: Optional[str] = None) -> str:
        sql_cfg = self._config.get("connection", {})
        driver = sql_cfg.get("driver", "{ODBC Driver 18 for SQL Server}")
        server = sql_cfg.get("server")
        if not server:
            raise BlueprintError("SQL connection server must be provided in config.sql.connection.server")
        database = database or sql_cfg.get("database")
        auth_mode = (sql_cfg.get("authentication") or "ServicePrincipal").lower()
        encrypt = sql_cfg.get("encrypt", True)
        trust_cert = sql_cfg.get("trustServerCertificate", False)
        parts = [
            f"Driver={driver}",
            f"Server={server}",
        ]
        if database:
            parts.append(f"Database={database}")

        if auth_mode in {"serviceprincipal", "aadserviceprincipal"}:
            tenant_id = sql_cfg.get("tenantId")
            client_id = sql_cfg.get("clientId")
            client_secret = sql_cfg.get("clientSecret")
            if not all([tenant_id, client_id, client_secret]):
                raise BlueprintError("Service principal authentication requires tenantId, clientId and clientSecret")
            parts.extend(
                [
                    "Authentication=ActiveDirectoryServicePrincipal",
                    f"User ID={client_id}",
                    f"Password={client_secret}",
                    f"Authority Id={tenant_id}",
                ]
            )
        elif auth_mode in {"managedidentity", "msi"}:
            parts.append("Authentication=ActiveDirectoryMsi")
        elif auth_mode in {"aadintegrated", "integrated"}:
            parts.append("Authentication=ActiveDirectoryIntegrated")
        elif auth_mode in {"sql", "sqlpassword"}:
            user = sql_cfg.get("username")
            password = sql_cfg.get("password")
            if not all([user, password]):
                raise BlueprintError("SQL authentication requires username and password")
            parts.extend([f"UID={user}", f"PWD={password}"])
        else:
            raise BlueprintError(f"Unsupported authentication mode: {auth_mode}")

        if encrypt:
            parts.append("Encrypt=Yes")
        if trust_cert:
            parts.append("TrustServerCertificate=Yes")

        timeout = self._config.get("options", {}).get("commandTimeoutSeconds")
        if timeout:
            parts.append(f"Command Timeout={timeout}")

        return ";".join(parts)

    def _connect(self, database: Optional[str] = None):
        if self._offline:
            raise BlueprintError("Cannot connect when running in offline mode")
        if self._connection is not None:
            return self._connection
        conn_str = self._build_connection_string(database)
        LOGGER.debug("Connecting to SQL using %s", conn_str)
        self._connection = self._pyodbc.connect(conn_str, autocommit=True)  # type: ignore[arg-type]
        return self._connection

    def _execute_non_query(self, sql: str, database: Optional[str] = None):
        if self._offline:
            LOGGER.info("[offline] Would execute SQL:\n%s", sql.strip())
            return
        connection = self._connect(database)
        LOGGER.debug("Executing SQL (%s chars)", len(sql))
        with connection.cursor() as cursor:
            cursor.execute(sql)

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    # ------------------------------------------------------------------
    # Schema & data management
    # ------------------------------------------------------------------
    def ensure_database(self):
        options = self._config.get("options", {})
        if not options.get("createDatabaseIfNotExists", False) or self._offline:
            return
        database_name = self._config.get("connection", {}).get("database")
        if not database_name:
            raise BlueprintError("Database name must be provided to create database")
        sql = (
            "IF DB_ID(?) IS NULL BEGIN DECLARE @sql nvarchar(max) = 'CREATE DATABASE ' + QUOTENAME(?) ; EXEC(@sql); END"
        )
        conn_master = self._connect("master")
        with conn_master.cursor() as cursor:
            cursor.execute(sql, database_name, database_name)

    def apply_package(self, package_path: Path):
        package = load_json(package_path)
        connection = None if self._offline else self._connect()
        if not self._offline:
            connection = self._connect()
        for block in package:
            for key in ("queries_schemas", "queries_tables", "queries_logging"):
                for statement in block.get(key, []) or []:
                    self._execute_non_query(statement)

    def seed_domains(self, seeds: Iterable[Mapping[str, Any]]):
        if self._offline:
            LOGGER.info("[offline] Seed skipped")
            return
        connection = self._connect()
        for entry in seeds:
            with connection.cursor() as cursor:
                cursor.execute(
                    "EXEC integration.sp_UpsertDomain ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
                    entry["name"],
                    entry.get("code", entry["name"].upper()),
                    entry.get("displayName", entry["name"].title()),
                    entry.get("description"),
                    entry.get("owner"),
                    entry.get("classification"),
                    entry.get("sensitivityTag"),
                    entry.get("hasSensitiveData", False),
                    (entry.get("retention") or {}).get("policy"),
                    (entry.get("retention") or {}).get("days"),
                    entry.get("dataQualityRuleset"),
                    ",".join(entry.get("tags", []) or []),
                )

            layers_cfg = entry.get("layers", {})
            required_layers = set(layers_cfg.get("required", []))
            optional_layers_cfg = layers_cfg.get("optional", {})

            for layer_key, template in self._layer_templates.items():
                is_required = layer_key in required_layers or template.workspace_role in {"landing", "silver", "gold"}
                enabled = optional_layers_cfg.get(layer_key, {}).get("enabled", False) if not is_required else True
                if not enabled:
                    continue
                with connection.cursor() as cursor:
                    cursor.execute(
                        "EXEC integration.sp_UpsertDomainLayer ?, ?, ?, ?, ?, ?",
                        entry["name"],
                        layer_key,
                        template.code,
                        template.workspace_role,
                        1 if is_required else 0,
                        1,
                    )

            env_map = entry.get("environments", {})
            for env_name, env_layers in env_map.items():
                for layer_key, workspace_payload in (env_layers or {}).items():
                    if layer_key not in self._layer_templates:
                        continue
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "EXEC integration.sp_UpsertDomainWorkspace ?, ?, ?, ?, ?, ?, ?, ?",
                            entry["name"],
                            layer_key,
                            env_name,
                            workspace_payload["workspaceGuid"],
                            workspace_payload["workspaceName"],
                            workspace_payload.get("ciCdStage"),
                            workspace_payload.get("deploymentMode"),
                            workspace_payload.get("isActive", True),
                        )

            for semantic in entry.get("semanticModels", []) or []:
                layer_key = semantic.get("layerKey") or semantic.get("workspaceLayer")
                if not layer_key:
                    continue
                with connection.cursor() as cursor:
                    cursor.execute(
                        "EXEC integration.sp_UpsertSemanticModel ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
                        entry["name"],
                        layer_key,
                        semantic["name"],
                        semantic.get("datasetName", semantic["name"]),
                        semantic.get("workspaceLayer", layer_key),
                        semantic.get("refreshPipeline"),
                        ",".join(semantic.get("tags", []) or []),
                        semantic.get("classification"),
                        semantic.get("hasSensitiveData", False),
                        semantic.get("retentionDays"),
                        semantic.get("isActive", True),
                    )

            for table in entry.get("tables", []) or []:
                layer_key = table.get("layerKey")
                table_name = table.get("name")
                if not layer_key or not table_name:
                    continue
                with connection.cursor() as cursor:
                    retention = table.get("retention") or {}
                    cursor.execute(
                        "EXEC integration.sp_UpsertDomainTable ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
                        entry["name"],
                        layer_key,
                        table.get("schema"),
                        table_name,
                        table.get("environment"),
                        table.get("displayName"),
                        table.get("description"),
                        table.get("classification"),
                        table.get("sensitivityTag"),
                        table.get("hasSensitiveData", False),
                        retention.get("policy"),
                        retention.get("days"),
                        table.get("dataQualityRuleset"),
                        ",".join(table.get("tags", []) or []),
                        table.get("isActive", True),
                    )

            for entity in entry.get("entities", []) or []:
                layer_key = entity.get("layerKey")
                if not layer_key:
                    continue
                with connection.cursor() as cursor:
                    cursor.execute(
                        "EXEC integration.sp_UpsertDomainEntity ?, ?, ?, ?, ?, ?, ?",
                        entry["name"],
                        layer_key,
                        entity.get("entityType"),
                        entity.get("entityId"),
                        ",".join(entity.get("governanceTags", []) or []),
                        entity.get("qualityRuleset"),
                        entity.get("isActive", True),
                    )

    def fetch_domains(self) -> List[DomainData]:
        if self._offline:
            raise BlueprintError("SQL fetch not available in offline mode")
        connection = self._connect()
        domains: Dict[int, DomainData] = {}
        layer_index: Dict[int, DomainLayerData] = {}

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DomainId, Name, Code, DisplayName, Description, Owner,
                       Classification, SensitivityTag, HasSensitiveData,
                       RetentionPolicy, RetentionDays, DataQualityRuleset, Tags
                FROM integration.Domain
                WHERE IsActive = 1
                ORDER BY Name
                """
            )
            for row in cursor.fetchall():
                domain = DomainData(
                    name=row.Name,
                    code=row.Code,
                    display_name=row.DisplayName,
                    description=row.Description,
                    owner=row.Owner,
                    classification=row.Classification,
                    sensitivity_tag=row.SensitivityTag,
                    has_sensitive_data=row.HasSensitiveData,
                    retention_policy=row.RetentionPolicy,
                    retention_days=row.RetentionDays,
                    data_quality_ruleset=row.DataQualityRuleset,
                    tags=parse_tags(row.Tags),
                )
                domains[row.DomainId] = domain

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DomainLayerId, DomainId, LayerKey, LayerCode, WorkspaceRole, IsRequired, IsActive
                FROM integration.DomainLayer
                WHERE IsActive = 1
                ORDER BY DomainLayerId
                """
            )
            for row in cursor.fetchall():
                domain = domains.get(row.DomainId)
                if not domain:
                    continue
                layer = DomainLayerData(
                    layer_key=row.LayerKey,
                    layer_code=row.LayerCode,
                    workspace_role=row.WorkspaceRole,
                    required=bool(row.IsRequired),
                    active=bool(row.IsActive),
                )
                domain.layers[row.LayerKey] = layer
                layer_index[row.DomainLayerId] = layer

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DomainLayerId, EnvironmentName, WorkspaceGuid, WorkspaceName, CiCdStage, DeploymentMode
                FROM integration.DomainWorkspace
                WHERE IsActive = 1
                ORDER BY DomainLayerId, EnvironmentName
                """
            )
            for row in cursor.fetchall():
                layer = layer_index.get(row.DomainLayerId)
                if not layer:
                    continue
                workspace = DomainLayerWorkspace(
                    environment=row.EnvironmentName,
                    workspace_guid=str(row.WorkspaceGuid),
                    workspace_name=row.WorkspaceName,
                    cicd_stage=row.CiCdStage,
                    deployment_mode=row.DeploymentMode,
                )
                layer.workspaces[row.EnvironmentName] = workspace

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT SemanticModelId, DomainLayerId, ModelName, DatasetName, WorkspaceLayer,
                       RefreshPipeline, Tags, Classification, HasSensitiveData, RetentionDays, IsActive
                FROM integration.SemanticModel
                WHERE IsActive = 1
                ORDER BY DomainLayerId, ModelName
                """
            )
            for row in cursor.fetchall():
                layer = layer_index.get(row.DomainLayerId)
                if not layer:
                    continue
                model = DomainSemanticModel(
                    name=row.ModelName,
                    dataset_name=row.DatasetName,
                    layer_key=row.WorkspaceLayer,
                    refresh_pipeline=row.RefreshPipeline,
                    tags=parse_tags(row.Tags),
                    classification=row.Classification,
                    has_sensitive_data=row.HasSensitiveData,
                    retention_days=row.RetentionDays,
                )
                layer.semantic_models.append(model)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DomainLayerId, EntityType, EntityId, GovernanceTags, QualityRuleset
                FROM integration.DomainEntity
                WHERE IsActive = 1
                ORDER BY DomainLayerId, EntityType, EntityId
                """
            )
            for row in cursor.fetchall():
                layer = layer_index.get(row.DomainLayerId)
                if not layer:
                    continue
                layer.entities.append(
                    {
                        "entityType": row.EntityType,
                        "entityId": row.EntityId,
                        "governanceTags": parse_tags(row.GovernanceTags),
                        "qualityRuleset": row.QualityRuleset,
                    }
                )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DomainLayerId, EnvironmentName, SchemaName, TableName, DisplayName, Description,
                       Classification, SensitivityTag, HasSensitiveData, RetentionPolicy, RetentionDays,
                       DataQualityRuleset, Tags
                FROM integration.DomainTable
                WHERE IsActive = 1
                ORDER BY DomainLayerId, SchemaName, TableName, EnvironmentName
                """
            )
            for row in cursor.fetchall():
                layer = layer_index.get(row.DomainLayerId)
                if not layer:
                    continue
                layer.tables.append(
                    DomainTable(
                        schema_name=row.SchemaName or "dbo",
                        table_name=row.TableName,
                        display_name=row.DisplayName,
                        description=row.Description,
                        environment=row.EnvironmentName,
                        classification=row.Classification,
                        sensitivity_tag=row.SensitivityTag,
                        has_sensitive_data=row.HasSensitiveData,
                        retention_policy=row.RetentionPolicy,
                        retention_days=row.RetentionDays,
                        data_quality_ruleset=row.DataQualityRuleset,
                        tags=parse_tags(row.Tags),
                    )
                )

        return [domains[key] for key in sorted(domains.keys(), key=lambda x: domains[x].name.lower())]


def parse_tags(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def build_layer_templates(config: Mapping[str, Any]) -> Dict[str, LayerTemplate]:
    templates: Dict[str, LayerTemplate] = {}
    layers_cfg = config.get("layers", {})
    for section in ("required", "optional"):
        for key, payload in (layers_cfg.get(section, {}) or {}).items():
            template = LayerTemplate(
                key=key,
                code=payload["code"],
                workspace_role=payload.get("workspaceRole", key),
                description=payload.get("description"),
                governance=payload.get("governance", {}),
                artifact_defaults=payload.get("artifactDefaults", {}),
            )
            templates[key] = template
    return templates


def ensure_output_directory(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def render_layer_governance(domain: DomainData, layer: DomainLayerData, template: LayerTemplate) -> Dict[str, Any]:
    governance = dict(template.governance)
    if domain.classification:
        governance.setdefault("classification", domain.classification)
    if domain.sensitivity_tag:
        governance.setdefault("sensitivityTag", domain.sensitivity_tag)
    if domain.has_sensitive_data is not None:
        governance.setdefault("hasSensitiveData", domain.has_sensitive_data)
    if domain.retention_days:
        governance.setdefault("retentionDays", domain.retention_days)
    if domain.retention_policy:
        governance.setdefault("retentionPolicy", domain.retention_policy)
    if domain.data_quality_ruleset:
        governance.setdefault("dataQualityRuleset", domain.data_quality_ruleset)
    return governance


def render_layer_lakehouses(domain: DomainData, template: LayerTemplate) -> List[Dict[str, Any]]:
    lakehouses: List[Dict[str, Any]] = []
    for entry in template.artifact_defaults.get("lakehouses", []) or []:
        lakehouses.append(
            {
                **entry,
                "name": entry.get("name", "").format(domain=domain.name, domain_code=domain.code),
            }
        )
    return lakehouses


def render_table_governance(domain: DomainData, table: DomainTable, template: Optional[LayerTemplate]) -> Dict[str, Any]:
    governance: Dict[str, Any] = {}
    template_defaults = dict(template.governance) if template else {}

    def apply_default(key: str, value: Any):
        if value is not None and value != "":
            governance[key] = value

    apply_default("classification", table.classification or template_defaults.get("classification") or domain.classification)
    apply_default("sensitivityTag", table.sensitivity_tag or template_defaults.get("sensitivityTag") or domain.sensitivity_tag)
    if table.has_sensitive_data is not None:
        governance["hasSensitiveData"] = table.has_sensitive_data
    elif domain.has_sensitive_data is not None:
        governance.setdefault("hasSensitiveData", domain.has_sensitive_data)
    apply_default("retentionPolicy", table.retention_policy or template_defaults.get("retentionPolicy") or domain.retention_policy)
    apply_default("retentionDays", table.retention_days or template_defaults.get("retentionDays") or domain.retention_days)
    apply_default(
        "dataQualityRuleset",
        table.data_quality_ruleset or template_defaults.get("dataQualityRuleset") or domain.data_quality_ruleset,
    )
    return governance


def render_table_entry(domain: DomainData, table: DomainTable, template: Optional[LayerTemplate]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "schema": table.schema_name,
        "name": table.table_name,
        "displayName": table.display_name,
        "description": table.description,
        "environment": table.environment,
        "governance": render_table_governance(domain, table, template),
        "tags": table.tags or domain.tags,
    }
    return payload


def write_manifest(
    output_root: Path,
    environment_name: str,
    domains: List[DomainData],
    layer_templates: Mapping[str, LayerTemplate],
    env_config: Mapping[str, Any],
) -> None:
    ensure_output_directory(output_root / environment_name)
    manifest_path = output_root / environment_name / "manifest.json"
    generated = dt.datetime.utcnow().isoformat() + "Z"
    manifest: Dict[str, Any] = {
        "environment": environment_name,
        "displayName": env_config.get("displayName", environment_name.title()),
        "generatedAt": generated,
        "domains": [],
    }
    for domain in domains:
        domain_entry = {
            "name": domain.name,
            "code": domain.code,
            "displayName": domain.display_name,
            "owner": domain.owner,
            "tags": domain.tags,
            "layers": [],
        }
        for layer_key, layer in domain.layers.items():
            workspace = layer.workspaces.get(environment_name)
            if not workspace:
                continue
            template = layer_templates.get(layer_key)
            layer_entry = {
                "key": layer.layer_key,
                "code": layer.layer_code,
                "workspaceRole": layer.workspace_role,
                "required": layer.required,
                "workspace": {
                    "guid": workspace.workspace_guid,
                    "name": workspace.workspace_name,
                    "ciCdStage": workspace.cicd_stage or env_config.get("cicdStage"),
                    "deploymentMode": workspace.deployment_mode,
                },
                "governance": render_layer_governance(domain, layer, template) if template else {},
                "lakehouses": render_layer_lakehouses(domain, template) if template else [],
                "semanticModels": [
                    {
                        "name": model.name,
                        "datasetName": model.dataset_name,
                        "refreshPipeline": model.refresh_pipeline,
                        "tags": model.tags,
                        "classification": model.classification,
                        "hasSensitiveData": model.has_sensitive_data,
                        "retentionDays": model.retention_days,
                    }
                    for model in layer.semantic_models
                    if model.layer_key == layer.layer_key
                ],
                "entities": layer.entities,
                "tables": [
                    render_table_entry(domain, table, template)
                    for table in layer.tables
                    if table.environment in (None, environment_name)
                ],
            }
            domain_entry["layers"].append(layer_entry)
        if domain_entry["layers"]:
            manifest["domains"].append(domain_entry)
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    LOGGER.info("Wrote manifest %s", manifest_path)


def write_governance_files(
    output_root: Path,
    environment_name: str,
    domains: List[DomainData],
    layer_templates: Mapping[str, LayerTemplate],
):
    env_root = output_root / environment_name
    ensure_output_directory(env_root)
    for domain in domains:
        for layer_key, layer in domain.layers.items():
            workspace = layer.workspaces.get(environment_name)
            if not workspace:
                continue
            template = layer_templates.get(layer_key)
            folder = env_root / f"{domain.code.lower()}_{layer.layer_code.lower()}"
            ensure_output_directory(folder)
            readme_path = folder / "README.md"
            readme_contents = [
                f"# {domain.display_name} — {layer.layer_code}",
                "",
                f"Workspace role: **{layer.workspace_role}**",
                "",
                "This folder will hold deployment artefacts generated from the SQL metadata.",
            ]
            readme_path.write_text("\n".join(readme_contents), encoding="utf-8")

            governance_path = folder / "governance.yaml"
            payload = {
                "domain": {
                    "name": domain.name,
                    "code": domain.code,
                    "displayName": domain.display_name,
                    "owner": domain.owner,
                    "classification": domain.classification,
                    "sensitivityTag": domain.sensitivity_tag,
                    "retentionPolicy": domain.retention_policy,
                    "retentionDays": domain.retention_days,
                    "dataQualityRuleset": domain.data_quality_ruleset,
                    "tags": domain.tags,
                },
                "layer": {
                    "key": layer.layer_key,
                    "code": layer.layer_code,
                    "workspaceRole": layer.workspace_role,
                    "workspace": {
                        "guid": workspace.workspace_guid,
                        "name": workspace.workspace_name,
                    },
                },
                "controls": render_layer_governance(domain, layer, template) if template else {},
            }
            with governance_path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(payload, handle, sort_keys=False)

            tables_payload = [
                render_table_entry(domain, table, template)
                for table in layer.tables
                if table.environment in (None, environment_name)
            ]
            if tables_payload:
                tables_path = folder / "tables.yaml"
                with tables_path.open("w", encoding="utf-8") as handle:
                    yaml.safe_dump(tables_payload, handle, sort_keys=False)


def build_manifests(
    config: Mapping[str, Any],
    output_root: Path,
    domains: List[DomainData],
    layer_templates: Mapping[str, LayerTemplate],
    environments: Optional[Iterable[str]] = None,
):
    env_cfg = config.get("environments", {})
    env_names = list(environments or env_cfg.keys())
    for env_name in env_names:
        env_settings = env_cfg.get(env_name)
        if not env_settings:
            LOGGER.warning("Environment %s not defined in config; skipping", env_name)
            continue
        write_manifest(output_root, env_name, domains, layer_templates, env_settings)
        write_governance_files(output_root, env_name, domains, layer_templates)

    index_path = output_root / "manifests.index.json"
    index_payload = {
        "generatedAt": dt.datetime.utcnow().isoformat() + "Z",
        "environments": env_names,
    }
    with index_path.open("w", encoding="utf-8") as handle:
        json.dump(index_payload, handle, indent=2)


def configure_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to the blueprint YAML config")
    parser.add_argument(
        "--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Directory where manifests will be generated"
    )
    parser.add_argument(
        "--environments",
        nargs="*",
        help="Specific environments to build manifests for (default: all from config)",
    )
    parser.add_argument("--offline", action="store_true", help="Do not connect to SQL; rely on seedDomains only")
    parser.add_argument(
        "--apply-sql", action="store_true", help="Execute the SQL deployment package before generating manifests"
    )
    parser.add_argument(
        "--seed", action="store_true", help="Seed the SQL database with seedDomains entries from the configuration"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    config = load_yaml(args.config)
    if not config:
        raise BlueprintError("Configuration file is empty")

    layer_templates = build_layer_templates(config)
    if not layer_templates:
        raise BlueprintError("No layer templates found in configuration")

    output_root = args.output_root
    ensure_output_directory(output_root)

    offline = args.offline
    sql_cfg = config.get("sql", {})
    package_path = Path(sql_cfg.get("deploymentPackage", DEFAULT_PACKAGE_PATH))

    data_source: Optional[SqlDataSource] = None
    domains: List[DomainData]

    if offline:
        LOGGER.info("Running in offline mode; using seedDomains only")
        data_source = None
        offline_source = OfflineDataSource(config, layer_templates)
        domains = offline_source.fetch_domains()
    else:
        sql_connection_cfg = sql_cfg.get("connection")
        if not sql_connection_cfg:
            raise BlueprintError("SQL connection details are required unless running in offline mode")
        data_source = SqlDataSource(sql_cfg, layer_templates, offline=False)
        try:
            data_source.ensure_database()
            if args.apply_sql:
                LOGGER.info("Applying SQL deployment package %s", package_path)
                data_source.apply_package(package_path)
            if args.seed:
                LOGGER.info("Seeding SQL database with domains from configuration")
                data_source.seed_domains(config.get("seedDomains", []) or [])
            domains = data_source.fetch_domains()
        finally:
            data_source.close()

    build_manifests(config, output_root, domains, layer_templates, args.environments)
    LOGGER.info("Completed blueprint deployment scaffolding")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BlueprintError as exc:
        LOGGER.error(str(exc))
        sys.exit(1)
