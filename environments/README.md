# Generated environment manifests

The `setup/fabric_blueprint_deployer.py` script materialises environment manifests and governance scaffolding here based on the domain definitions stored in the Fabric SQL orchestration database.  The directory is empty in source control so that environments can be created or removed dynamically at deployment time.

Run the deployer with the configuration in `config/blueprint.yaml` to generate stage-specific assets locally or inside CI/CD pipelines.
