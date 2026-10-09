"""Prepare a fresh dbt manifest for local checks without warehouse credentials.

Only ``deps`` (package downloads) and ``parse`` (no warehouse connection) run.
See https://docs.getdbt.com/reference/commands/parse.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PROFILE = """analytics_layer:
  target: offline_validation
  outputs:
    offline_validation:
      type: bigquery
      method: service-account
      project: dbt-offline-validation
      dataset: offline_validation
      keyfile: /nonexistent/offline-validation-key.json
      location: US
      threads: 1
"""


def validation_environment(home: Path) -> dict[str, str]:
    """Use a minimal environment so ADC, production profiles and secrets stay out."""
    allowed = {
        "PATH",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "SYSTEMROOT",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        DBT_SEND_ANONYMOUS_USAGE_STATS="false",
        DBT_PARTIAL_PARSE="false",
        GOOGLE_APPLICATION_CREDENTIALS=str(home / "nonexistent-key.json"),
    )
    return env


def prepare(project: Path) -> None:
    """Install locked packages when needed, then always parse current source."""
    lock_path = project / "package-lock.yml"
    original_lock = lock_path.read_bytes()
    lock = yaml.safe_load(original_lock)
    packages = lock.get("packages", [])
    if not packages or any(
        not item.get("version") or not item.get("name") for item in packages
    ):
        raise ValueError("A populated version-pinned dbt package-lock.yml is required.")
    fingerprint = hashlib.sha256(
        original_lock + (project / "packages.yml").read_bytes()
    ).hexdigest()
    package_dir = project / "dbt_packages"
    stamp = package_dir / ".validation-lock.sha256"
    installed = all(
        (package_dir / item["name"] / "dbt_project.yml").is_file() for item in packages
    )
    matches = stamp.is_file() and stamp.read_text(encoding="utf-8") == fingerprint
    with tempfile.TemporaryDirectory(prefix="dbt-offline-checks-") as directory:
        home = Path(directory)
        profiles = home / "profiles"
        profiles.mkdir()
        (profiles / "profiles.yml").write_text(PROFILE, encoding="utf-8")
        env = validation_environment(home)

        def run(command: str, project_dir: Path = project) -> None:
            args = [
                sys.executable,
                "-c",
                "from dbt.cli.main import cli; cli()",
                "--no-send-anonymous-usage-stats",
                "--no-partial-parse",
                command,
                "--project-dir",
                str(project_dir),
                "--profiles-dir",
                str(profiles),
                "--target",
                "offline_validation",
            ]
            subprocess.run(args, cwd=project_dir, env=env, check=True)

        # Remove stale output first so failed parsing cannot certify an older manifest.
        target = project / "target"
        target.mkdir(exist_ok=True)
        manifest = target / "manifest.json"
        manifest.unlink(missing_ok=True)
        if not installed or not matches:
            # Resolve exact locked versions in an isolated dependency project.
            # dbt may refresh its lock hash across versions; never rewrite the
            # repository's dependency declarations or lock during validation.
            bootstrap = home / "dependencies"
            bootstrap.mkdir()
            (bootstrap / "dbt_project.yml").write_text(
                "name: offline_dependencies\nversion: '1.0'\nprofile: analytics_layer\n",
                encoding="utf-8",
            )
            (bootstrap / "packages.yml").write_text(
                yaml.safe_dump(
                    {
                        "packages": [
                            {"package": item["package"], "version": item["version"]}
                            for item in packages
                        ]
                    }
                ),
                encoding="utf-8",
            )
            run("deps", bootstrap)
            package_dir.mkdir(exist_ok=True)
            for item in packages:
                destination = package_dir / item["name"]
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(bootstrap / "dbt_packages" / item["name"], destination)
            stamp.write_text(fingerprint, encoding="utf-8")
        run("parse")
        if not manifest.is_file():
            raise RuntimeError("dbt parse did not generate target/manifest.json.")


def main() -> int:
    try:
        prepare(Path(__file__).resolve().parents[1] / "analytics_layer")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Offline dbt validation preparation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
