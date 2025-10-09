# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This repository builds container images for CloudNativePG (CNPG) containing PostgreSQL with TimescaleDB and PostGIS extensions. It's a fork of https://github.com/imusmanmalik/cloudnative-pg-cnpg-cinnamon-containers.

The images are built on top of the PostGIS Debian images and include:
- TimescaleDB (time-series database extension)
- PostGIS (geospatial extension)
- Barman Cloud (backup and recovery tool)
- PGAudit (audit logging extension)
- pg-failover-slots
- pgrouting

Images are published to GitHub Container Registry at `ghcr.io/gfx-labs/cnpg-cinnamon`.

## Build Architecture

### Version Management

Each PostgreSQL version (16-17) has its own directory under `cinnamon/`:
- `cinnamon/<version>/` - Contains the Dockerfile and metadata for each PG version
- `cinnamon/<version>/.versions.json` - Tracks component versions and release numbers

The `.versions.json` file contains:
- `POSTGIS_IMAGE_VERSION` - Base PostGIS image tag (e.g., "16-3.5")
- `POSTGIS_IMAGE_LAST_UPDATED` - Timestamp to detect upstream changes
- `BARMAN_VERSION` - Version of Barman backup tool
- `IMAGE_RELEASE_VERSION` - Incremental release number for this image

### Automated Update Process

The repository uses a sophisticated update mechanism:

1. **Daily Updates** (`.github/workflows/update.yml`):
   - Runs daily at midnight or via manual dispatch
   - Executes `cinnamon/update.sh` to check for upstream changes
   - Updates are committed automatically to the main branch

2. **Update Script** (`cinnamon/update.sh`):
   - Queries Docker Hub API for latest PostGIS base images
   - Checks PyPI for latest Barman version
   - Compares timestamps and versions in `.versions.json`
   - Increments `IMAGE_RELEASE_VERSION` when components change
   - Resets to version 1 when base PostGIS image changes
   - Generates Dockerfiles from templates
   - Updates Python requirements with `pip-compile --generate-hashes`

3. **Build Strategy** (`.github/generate-strategy.sh`):
   - Generates a JSON matrix for GitHub Actions
   - Queries Docker Hub API to detect ARM64 support per version
   - Automatically falls back to amd64-only when ARM64 unavailable
   - Creates multiple tags for each image:
     - Major version only (e.g., "16")
     - Major + PostGIS version (e.g., "16-3.5")
     - Full version tag (e.g., "16-3.5-77")
     - "latest" alias (currently points to PG 17)

### Build Pipeline

The Continuous Delivery workflow (`.github/workflows/build.yml`):
1. **Trigger**: Pushes to main branch or manual workflow dispatch
2. **Generate Jobs**: Runs `generate-strategy.sh` to create build matrix
3. **Build**: For each PostgreSQL version:
   - Sets up QEMU for multi-platform builds
   - Checks if primary tag already exists (to avoid overwrites)
   - Builds and loads image locally
   - Runs Dockle security scan
   - Pushes to both testing and production registries (on main branch)

## Common Commands

### Running the Update Script
```bash
# Update all versions
./cinnamon/update.sh

# Update specific version(s)
./cinnamon/update.sh 16 17
```

### Testing Build Strategy Generation
```bash
# Generate and view the build matrix
bash .github/generate-strategy.sh
```

### Building Images Locally
```bash
# Build a specific version
cd cinnamon/16
docker build -t cnpg-cinnamon:16-test .

# Multi-platform build (requires buildx)
docker buildx build --platform linux/amd64,linux/arm64 -t cnpg-cinnamon:16-test .
```

### Updating Python Dependencies
```bash
# Install pip-tools
pip3 install --upgrade pip-tools

# Regenerate requirements.txt from requirements.in
cd cinnamon
pip-compile --generate-hashes requirements.in
```

## Key Architectural Decisions

### Template-Based Dockerfile Generation

Dockerfiles are generated from templates (`Dockerfile.template` and `Dockerfile-beta.template`):
- `%%POSTGIS_IMAGE_VERSION%%` - Replaced with PostGIS base image tag
- `%%IMAGE_RELEASE_VERSION%%` - Replaced with incremental release number

The update script copies files from `src/` and processes templates for each version directory.

### Multi-Platform Support Detection

Platform support (amd64/arm64) is automatically detected by querying Docker Hub's API for each PostGIS base image. This prevents build failures when ARM64 is unavailable for specific versions.

### Release Version Semantics

- `IMAGE_RELEASE_VERSION` resets to 1 when the PostGIS base image changes
- Increments by 1 when Barman or PostGIS base image timestamp changes
- This creates a versioning scheme: `<pg-major>-<postgis-version>-<release>`

### Tag Immutability

The build pipeline checks if a primary tag already exists before building. If it exists:
- Skip the build to preserve tag consistency
- Retrieve the existing digest for the image catalog

This ensures that once a tag is published, its SHA digest never changes.

### GitHub Actions Permissions

The workflows use a Personal Access Token (`REPO_GHA_PAT`) to:
- Temporarily disable branch protection
- Commit automated updates to the main branch
- Re-enable branch protection

This is necessary because the default `GITHUB_TOKEN` cannot bypass branch protection rules.

## Working with CloudNativePG

To use these images in a CloudNativePG cluster:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: cluster-example
spec:
  instances: 1
  imageName: ghcr.io/gfx-labs/cnpg-cinnamon:16
  bootstrap:
    initdb:
      postInitTemplateSQL:
        - CREATE EXTENSION timescaledb;
        - CREATE EXTENSION postgis;
  postgresql:
    shared_preload_libraries:
      - timescaledb
  storage:
    size: 1Gi
```

The `shared_preload_libraries` setting is required for TimescaleDB to function properly.

## Important Configuration

### PostgreSQL Version Support

- Currently supports PostgreSQL 16 and 17
- Update `POSTGRESQL_LATEST_MAJOR_RELEASE` in `update.sh` when new major versions are released
- Beta versions (>17) use `Dockerfile-beta.template`

### User ID

All images run as user ID 26 (postgres user), modified from the default UID to match CloudNativePG requirements.

### Security Scanning

Dockle scan is configured to accept certain keywords and filenames that contain "key" or "password" but are safe (templates, documentation, test certificates).
