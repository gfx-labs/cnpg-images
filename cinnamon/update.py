#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError


# Update this every time a new major release of PostgreSQL is available
POSTGRESQL_LATEST_MAJOR_RELEASE = 18


def fetch_postgres_image_version(version: str, item: str) -> str:
    """
    Fetch the latest PostGIS image version or last_updated timestamp from Docker Hub.

    Args:
        version: PostgreSQL major version (e.g., "16", "17", "18")
        item: "name" or "last_updated"

    Returns:
        The requested value as a string
    """
    # Determine the regex pattern based on version
    if int(version) > POSTGRESQL_LATEST_MAJOR_RELEASE:
        pattern = rf"^{version}beta[0-9]+-master$"
    else:
        pattern = rf"^{version}-[0-9.]+$"

    url = f"https://registry.hub.docker.com/v2/repositories/postgis/postgis/tags/?name={version}&ordering=last_updated&"

    print(f"  → Fetching PostGIS {item} for PostgreSQL {version} from Docker Hub...")

    try:
        with urlopen(url) as response:
            data = json.loads(response.read().decode())
    except URLError as e:
        print(f"❌ Error fetching Docker Hub data: {e}")
        sys.exit(1)

    # Filter results matching the pattern and extract the requested item
    matches = []
    for result in data.get("results", []):
        if re.match(pattern, result.get("name", "")):
            matches.append(result.get(item))

    if not matches:
        return ""

    # Sort and return the latest
    matches.sort(reverse=True)
    result_value = matches[0]
    print(f"  ✓ Found {item}: {result_value}")
    return result_value


def get_latest_barman_version() -> str:
    """
    Get the latest Barman version.
    Currently hardcoded to 3.13.3.
    """
    # curl -s https://pypi.org/pypi/barman/json | jq -r '.releases | keys[]' | sort -Vr | head -n1
    # Set a fixed version of Barman to 3.13.3
    # The latest released version of Barman 3.13.0 introduced a change
    # in the argument list for the restore.
    # For more information check the following issue: cloudnative-pg/cloudnative-pg#6932
    return "3.16.2"


def get_timescaledb_version(version_file: Path) -> str:
    """
    Get the TimescaleDB version from the version file.
    TimescaleDB version is manually managed - update .versions.json to change it.

    Args:
        version_file: Path to .versions.json

    Returns:
        TimescaleDB version string
    """
    if version_file.exists():
        with open(version_file, 'r') as f:
            data = json.load(f)
        return data.get("TIMESCALEDB_VERSION", "")
    return ""


def record_version(version_file: Path, component: str, component_version: str | int):
    """
    Update a component version in the version file.

    Args:
        version_file: Path to .versions.json
        component: Component name (e.g., "BARMAN_VERSION")
        component_version: New version value
    """
    with open(version_file, 'r') as f:
        data = json.load(f)

    data[component] = str(component_version)

    with open(version_file, 'w') as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write('\n')


def generate_postgres(version: str):
    """
    Generate Dockerfile and update version tracking for a PostgreSQL version.

    Args:
        version: PostgreSQL major version (e.g., "16", "17", "18")
    """
    print(f"\n📦 Processing PostgreSQL {version}")
    print("=" * 60)

    version_dir = Path(version)
    version_file = version_dir / ".versions.json"
    image_release_version = 1

    # Fetch latest versions
    postgis_image_version = fetch_postgres_image_version(version, "name")
    if not postgis_image_version:
        print(f"❌ Unable to retrieve latest postgres {version} image version")
        sys.exit(1)

    postgis_image_last_update = fetch_postgres_image_version(version, "last_updated")
    if not postgis_image_last_update:
        print(f"❌ Unable to retrieve latest postgis {version} image version last update time")
        sys.exit(1)

    barman_version = get_latest_barman_version()
    if not barman_version:
        print("❌ Unable to retrieve latest barman-cli-cloud version")
        sys.exit(1)

    # Get TimescaleDB version (manually managed in .versions.json)
    timescaledb_version = get_timescaledb_version(version_file)
    if timescaledb_version:
        print(f"  → Using TimescaleDB version: {timescaledb_version}")

    # Handle existing or new version file
    if version_file.exists():
        print(f"  → Reading existing version file...")
        with open(version_file, 'r') as f:
            old_data = json.load(f)

        old_image_release_version = int(old_data.get("IMAGE_RELEASE_VERSION", 1))
        old_barman_version = old_data.get("BARMAN_VERSION", "")
        old_postgis_image_last_update = old_data.get("POSTGIS_IMAGE_LAST_UPDATED", "")
        old_postgis_image_version = old_data.get("POSTGIS_IMAGE_VERSION", "")
        image_release_version = old_image_release_version
    else:
        print(f"  → Creating new version file...")
        # Create new version file
        with open(version_file, 'w') as f:
            json.dump({}, f)

        record_version(version_file, "IMAGE_RELEASE_VERSION", image_release_version)
        record_version(version_file, "BARMAN_VERSION", barman_version)
        record_version(version_file, "POSTGIS_IMAGE_LAST_UPDATED", postgis_image_last_update)
        record_version(version_file, "POSTGIS_IMAGE_VERSION", postgis_image_version)

        # Copy src files and generate Dockerfile
        print(f"  → Copying source files...")
        copy_src_files(version)
        print(f"  → Generating Dockerfile...")
        generate_dockerfile(version, postgis_image_version, image_release_version, timescaledb_version)
        print(f"✅ Completed PostgreSQL {version}\n")
        return

    # Check for changes
    print(f"  → Checking for version changes...")
    new_release = False

    if old_postgis_image_last_update != postgis_image_last_update:
        print(f"  🔄 Debian Image changed from {old_postgis_image_last_update} to {postgis_image_last_update}")
        new_release = True
        record_version(version_file, "POSTGIS_IMAGE_LAST_UPDATED", postgis_image_last_update)

    if old_barman_version != barman_version:
        print(f"  🔄 Barman changed from {old_barman_version} to {barman_version}")
        new_release = True
        record_version(version_file, "BARMAN_VERSION", barman_version)

    if old_postgis_image_version != postgis_image_version:
        print(f"  🔄 PostGIS base image changed from {old_postgis_image_version} to {postgis_image_version}")
        record_version(version_file, "IMAGE_RELEASE_VERSION", 1)
        record_version(version_file, "POSTGIS_IMAGE_VERSION", postgis_image_version)
        image_release_version = 1
    elif new_release:
        image_release_version = old_image_release_version + 1
        record_version(version_file, "IMAGE_RELEASE_VERSION", image_release_version)
        print(f"  🔄 Incrementing release version to {image_release_version}")
    else:
        print(f"  ℹ️  No version changes detected")

    # Copy src files and generate Dockerfile
    print(f"  → Copying source files...")
    copy_src_files(version)
    print(f"  → Generating Dockerfile (release version: {image_release_version})...")
    generate_dockerfile(version, postgis_image_version, image_release_version, timescaledb_version)
    print(f"✅ Completed PostgreSQL {version}\n")


def copy_src_files(version: str):
    """Copy files from src/ to the version directory."""
    src_dir = Path("src")
    version_dir = Path(version)

    # Copy all files from src/ to version/
    for item in src_dir.iterdir():
        dest = version_dir / item.name
        if item.is_file():
            shutil.copy2(item, dest)
        elif item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)


def generate_dockerfile(version: str, postgis_image_version: str, image_release_version: int, timescaledb_version: str):
    """
    Generate Dockerfile from template.

    Args:
        version: PostgreSQL major version
        postgis_image_version: PostGIS image tag
        image_release_version: Release version number
        timescaledb_version: TimescaleDB version to verify
    """
    template_file = Path("Dockerfile.template")
    output_file = Path(version) / "Dockerfile"

    with open(template_file, 'r') as f:
        template_content = f.read()

    # Replace placeholders
    content = template_content.replace("%%POSTGIS_IMAGE_VERSION%%", postgis_image_version)
    content = content.replace("%%IMAGE_RELEASE_VERSION%%", str(image_release_version))
    content = content.replace("%%TIMESCALEDB_VERSION%%", timescaledb_version)

    with open(output_file, 'w') as f:
        f.write(content)


def update_requirements():
    """Update requirements.in and generate requirements.txt with uv."""
    print("\n🔧 Updating Python requirements")
    print("=" * 60)

    barman_version = get_latest_barman_version()
    print(f"  → Using Barman version: {barman_version}")

    # Write requirements.in
    requirements_in = Path("requirements.in")
    print(f"  → Writing requirements.in...")
    with open(requirements_in, 'w') as f:
        f.write(f"barman[cloud,azure,snappy,google,zstandard,lz4] == {barman_version}\n")

    # Generate requirements.txt with uv
    print(f"  → Running uv pip compile (this may take a moment)...")
    try:
        result = subprocess.run(
            ["uv", "pip", "compile", "--generate-hashes", "requirements.in", "-o", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"  ✓ Successfully compiled requirements")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running uv pip compile: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ Error: uv command not found. Please install uv.")
        sys.exit(1)

    # Remove psycopg from the list of packages (it's provided by the system)
    requirements_txt = Path("requirements.txt")
    print(f"  → Filtering out system-provided packages (psycopg)...")
    with open(requirements_txt, 'r') as f:
        lines = f.readlines()

    # Filter out psycopg and its dependencies (via barman)
    filtered_lines = []
    skip_until_blank = False

    for line in lines:
        # If we find psycopg, start skipping
        if line.startswith("psycopg"):
            skip_until_blank = True
            continue

        # If we're skipping and hit a line with "via barman", continue skipping
        if skip_until_blank:
            if "via barman" in line or line.strip().startswith("--hash"):
                continue
            else:
                skip_until_blank = False

        filtered_lines.append(line)

    with open(requirements_txt, 'w') as f:
        f.writelines(filtered_lines)

    # Move requirements.txt to src/
    print(f"  → Moving requirements.txt to src/...")
    shutil.move(requirements_txt, Path("src") / "requirements.txt")
    print(f"✅ Requirements updated\n")


def main():
    """Main entry point."""
    print("🚀 CloudNativePG Cinnamon Container Image Update Script")
    print("=" * 60)

    # Change to script directory
    script_dir = Path(__file__).parent.resolve()
    os.chdir(script_dir)

    # Supported PostgreSQL versions
    SUPPORTED_VERSIONS = ["16", "17", "18"]

    # Get versions from command line or use all supported versions
    versions = sys.argv[1:] if len(sys.argv) > 1 else SUPPORTED_VERSIONS

    print(f"Target versions: {', '.join(versions)}")

    # Validate versions
    for version in versions:
        if version not in SUPPORTED_VERSIONS:
            print(f"❌ Error: Version {version} is not supported. Supported versions: {', '.join(SUPPORTED_VERSIONS)}")
            sys.exit(1)

    # Update requirements first
    update_requirements()

    # Generate Dockerfiles for each version
    for version in sorted(versions):
        generate_postgres(version)

    print("\n" + "=" * 60)
    print("🎉 All done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
