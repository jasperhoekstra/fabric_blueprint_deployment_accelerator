# Domain-Aware Blueprint Expansion and Governance Controls

This plan extends the Fabric Metadata-Driven (FMD) deployment accelerator so that solution teams can declare domains, choose optional domain-specific layers, and enforce data governance controls (classification, tagging, privacy, retention). It assumes the existing DTAP (Dev, Test, Acceptance, Prod) street and Fabric SQL orchestration database.

## 1. Domain and layer modeling

1. Maintain a single blueprint configuration (`config/blueprint.yaml`) that captures layer templates, DTAP environments, and SQL connection details.
2. Store every domain, layer selection, workspace assignment, and governance override directly in the Fabric SQL orchestration database (`integration.Domain`, `integration.DomainLayer`, `integration.DomainWorkspace`, etc.).
3. Use the deployment CLI (`setup/fabric_blueprint_deployer.py`) to apply the SQL package, seed initial domains (optional), and emit environment manifests by reading the metadata from SQL.

## 2. Orchestration database enhancements

1. Extend the Fabric SQL schema to add domain-aware tables and governance metadata:
   - `integration.Domain`, `integration.DomainLayer`, `integration.DomainWorkspace` for structural relationships.
   - `integration.DomainTable` for table-level governance (classification, retention, sensitivity overrides) per domain/layer/environment.
   - `integration.SemanticModel`, `integration.SemanticLink` to capture curated and reporting semantics by domain.
2. Create stored procedures for idempotent updates (e.g., `sp_UpsertDomain`, `sp_UpsertDomainLayer`, `sp_UpsertDomainWorkspace`, `sp_UpsertDomainTable`, `sp_UpsertSemanticModel`, `sp_UpsertSemanticLink`) and query views that filter by environment, domain, layer, or governance requirement.
3. Document the ER model updates in `FMD_METADATA_MODEL.md`, including sample payloads for applying PII classifications, retention policies, semantic links, and table-level governance.

## 3. Asset hierarchy restructuring

1. Generate the environment → domain → layer scaffolding dynamically by running `python setup/fabric_blueprint_deployer.py --config config/blueprint.yaml`, which produces manifests and governance stubs in `environments/` based on the SQL metadata.
2. Keep shared templates (pipelines, notebooks, governance policies) under `templates/` and reference them during deployment using the manifest output rather than maintaining pre-generated per-domain folders in source control.
3. Update packaging scripts to consume the generated manifests during CI/CD, deploying only the domain/layer combinations that are active in SQL for the target environment.

## 4. Pipeline and notebook parameterization

1. Add environment, domain, and layer parameters to orchestration pipelines (e.g., `PL_FMD_LOAD_ALL`) so that activities query the orchestration DB with the appropriate filters and honor governance attributes (classification, retention).
2. Enhance variable libraries to inject governance settings (PII handling, masking options, retention schedules) alongside semantic model IDs, driven by configuration.
3. Modify notebooks to:
   - Retrieve governance metadata from the orchestration DB.
   - Apply data quality and governance measures during ingestion and transformation (e.g., masking PII, enforcing retention windows, tagging tables with classifications).
   - Publish semantic links/materialized views for the `3000_CURATED` gold layer and domain reporting workspaces, logging results back to governance tables.

## 5. Governance enforcement capabilities

1. Implement governance validation routines that run pre- and post-deployment:
   - Check for missing classifications or retention policies before promoting artifacts.
   - Verify semantic link definitions and materialized view refresh status.
   - Record results in audit tables for observability workspaces (`900x_DOMAIN_MONITORING`).
2. Provide policy-driven actions based on governance metadata:
   - Automatically schedule purge notebooks for entities with retention limits.
   - Trigger PII masking pipelines when sensitive columns are detected.
   - Propagate tags to Fabric item metadata for searchability and compliance reporting.
3. Surface governance dashboards in the monitoring workspace, fed from the orchestration database views and audit tables.

## 6. Deployment-as-code and DTAP automation

1. Evolve the setup notebook (or introduce a CLI) to generate infrastructure-as-code descriptors per environment, using manifests to create/update Fabric workspaces, lakehouses, semantic models, and governance artifacts.
2. Expand CI/CD definitions (Azure DevOps YAML or GitHub Actions) with stages for Dev → Test → Acc → Prod that:
   - Apply SQL migrations (including governance tables).
   - Deploy or update pipelines, notebooks, semantic models, and governance assets based on manifests.
   - Execute validation notebooks/tests covering data quality, governance, and semantic publishing.
   - Require approvals between stages, especially before promoting changes that adjust governance policies.
3. Include rollback and drift-detection steps to ensure environment parity and compliance across DTAP stages.

## 7. Change management and documentation

1. Update framework documentation to explain the domain catalog, optional layers, and governance controls.
2. Provide onboarding guides for domain teams to request new layers or adjust governance settings through configuration rather than manual operations.
3. Maintain version-controlled templates for governance policies, enabling traceable changes and audits.

Following this plan will allow the deployment accelerator to materialize environment-aware, domain-specific workspaces with configurable optional layers while embedding governance guardrails throughout ingestion, transformation, and semantic publishing.
