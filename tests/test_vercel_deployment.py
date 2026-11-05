"""Guards for the Vercel deployment contract.

The deployment ships the Dash application, its shared ``utils`` package and the
committed data artifacts. These tests fail when that contract is broken: a
missing runtime dependency, an ignored runtime file, or an entrypoint that no
longer exposes the WSGI callable Vercel loads.
"""

import ast
import fnmatch
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "my-dash-app"
ENTRYPOINT = ROOT / "wsgi.py"

# Runs the entrypoint exactly like the Vercel runtime does: import the file and
# read the top-level ``app`` name. The second argument lists the top-level
# modules that no runtime dependency provides; importing one of them fails the
# same way the deployment would fail.
ENTRYPOINT_PROBE = """
import importlib.util
import json
import sys
from pathlib import Path

blocked = set(json.loads(sys.argv[2]))


class BuildDependencyBlocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in blocked:
            raise ImportError(
                f"{name} is provided by a build-time dependency, "
                "not by a runtime dependency"
            )
        return None


sys.meta_path.insert(0, BuildDependencyBlocker())

root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("vercel_wsgi", root / "wsgi.py")
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)

dash_module = sys.modules["app"]
client = entrypoint.app.test_client()
landing = client.get("/")
dashboard = client.get("/dashboard")

print(json.dumps({
    "flask_app": type(entrypoint.app).__name__,
    "wsgi_callable": hasattr(entrypoint.app, "wsgi_app"),
    "server_is_entrypoint": dash_module.server is entrypoint.app,
    "dash_module_file": dash_module.__file__,
    "assets_folder": dash_module.app.config.assets_folder,
    "pages_folder": dash_module.app.config.pages_folder,
    "template_folder": entrypoint.app.template_folder,
    "landing_status": landing.status_code,
    "dashboard_status": dashboard.status_code,
    "dashboard_location": dashboard.headers.get("Location"),
}))
"""

# Directories under the app that hold build-time inputs rather than runtime
# files. The auth bundle is prebuilt into ``assets/``, and the cache directory
# only holds a leftover cache entry.
BUILD_INPUT_DIRECTORIES = ("auth_frontend", "cache-directory")

# Packages that only the build uses. The deployment guard is inert when none of
# them can be detected, so the test asserts that they were found.
KNOWN_BUILD_ONLY_MODULES = ("google", "sqlalchemy", "dbt", "pytest")

BUILD_ARTIFACTS = (
    "analytics_layer/dbt_project.yml",
    "analytics_layer/models/marts/sales.sql",
    "node_modules/left-pad/index.js",
    "data/raw/source_crm/customers.csv",
    "tests/test_auth.py",
    "Notebooks/analysis.ipynb",
    "my-dash-app/auth_frontend/main.js",
    ".venv/lib/python3.12/site-packages/dash/__init__.py",
    "package.json",
)


def runtime_files():
    """Return every file the deployed app reads at request time."""
    files = {"wsgi.py"}
    for base in (APP_DIR, ROOT / "utils"):
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if "__pycache__" in relative.parts:
                continue
            if any(part in BUILD_INPUT_DIRECTORIES for part in relative.parts):
                continue
            files.add(str(relative))
    return sorted(files)


def expand_braces(pattern):
    """Expand a node-glob brace group into its individual patterns."""
    if "{" not in pattern:
        return [pattern]
    start = pattern.index("{")
    end = pattern.index("}", start)
    head, body, tail = pattern[:start], pattern[start + 1 : end], pattern[end + 1 :]
    expanded = []
    for option in body.split(","):
        expanded.extend(expand_braces(head + option + tail))
    return expanded


def matches_rule(path, rule):
    """Approximate gitignore/node-glob matching for the rules used here."""
    rule = rule.strip().rstrip("/")
    if rule.startswith("/"):
        candidates = [rule[1:]]
    elif "/" in rule:
        candidates = [rule]
    else:
        candidates = [rule, f"**/{rule}"]
    for candidate in candidates:
        if fnmatch.fnmatch(path, candidate) or fnmatch.fnmatch(path, candidate + "/**"):
            return True
    return False


def is_ignored(path, rules):
    """Return whether the last matching rule ignores the path."""
    ignored = False
    for raw in rules:
        rule = raw.strip()
        if not rule or rule.startswith("#"):
            continue
        negated = rule.startswith("!")
        if negated:
            rule = rule[1:]
        if matches_rule(path, rule):
            ignored = not negated
    return ignored


def local_modules():
    """Map every importable module name in the app to its file."""
    modules = {}
    for path in APP_DIR.rglob("*.py"):
        _register_module(modules, path, APP_DIR)
    for path in (ROOT / "utils").rglob("*.py"):
        _register_module(modules, path, ROOT)
    modules["wsgi"] = ENTRYPOINT
    return modules


def _register_module(modules, path, base):
    """Register a module under its dotted name and under its package name."""
    relative = path.relative_to(base).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
        if parts:
            modules.setdefault(".".join(parts), path)
        return
    modules.setdefault(".".join(parts), path)
    if len(parts) > 1:
        modules.setdefault(".".join(parts[:-1]), path)


def _is_import_error(handler):
    """Return whether a except handler catches ImportError."""
    error_type = handler.type
    if isinstance(error_type, ast.Name):
        return error_type.id == "ImportError"
    if isinstance(error_type, ast.Tuple):
        return any(
            isinstance(element, ast.Name) and element.id == "ImportError"
            for element in error_type.elts
        )
    return False


def imported_names(path):
    """Return the absolute module names imported by a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
            _is_import_error(handler) for handler in node.handlers
        ):
            for statement in node.body:
                guarded.update(id(child) for child in ast.walk(statement))
    names = set()
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def reachable_imports():
    """Return the third-party modules reachable from the deployment entrypoint."""
    modules = local_modules()
    pending = [ENTRYPOINT]
    seen = set()
    third_party = set()
    while pending:
        path = pending.pop()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        for name in imported_names(path):
            local = None
            for candidate in (name, name.rsplit(".", 1)[0]):
                if candidate in modules:
                    local = modules[candidate]
                    break
            if local is None:
                third_party.add(name.split(".")[0])
                continue
            pending.append(local)
            pending.extend(sorted(local.parent.glob("*.py")))
    return third_party


def run_entrypoint_probe(blocked=()):
    """Boot the deployment entrypoint in a subprocess and report what it serves."""
    environment = dict(os.environ)
    environment.update(
        {
            "NEXT_PUBLIC_SUPABASE_URL": "https://project.supabase.co",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY": "test-anon-key",
            "AUTH_APP_ORIGIN": "https://dashboard.example.com",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            ENTRYPOINT_PROBE,
            str(ROOT),
            json.dumps(sorted(blocked)),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=environment,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout.strip().splitlines()[-1])


def modules_without_runtime_provider():
    """Return the top-level modules that no runtime dependency provides."""
    runtime = {name for name, _ in _pinned_packages(ROOT / "requirements.txt")}
    distributions = importlib.metadata.packages_distributions()
    return {
        module
        for module, providers in distributions.items()
        if module not in sys.stdlib_module_names
        and not any(
            provider.lower().replace("_", "-") in runtime for provider in providers
        )
    }


class EntrypointTest(unittest.TestCase):
    def test_entrypoint_exposes_the_wsgi_callable(self):
        report = run_entrypoint_probe()

        self.assertEqual(report["flask_app"], "Flask")
        self.assertTrue(report["wsgi_callable"])
        self.assertTrue(report["server_is_entrypoint"])
        self.assertEqual(
            Path(report["dash_module_file"]).resolve(),
            (APP_DIR / "app.py").resolve(),
        )
        self.assertEqual(
            Path(report["assets_folder"]).resolve(), (APP_DIR / "assets").resolve()
        )
        self.assertEqual(
            Path(report["pages_folder"]).resolve(), (APP_DIR / "pages").resolve()
        )
        self.assertEqual(
            Path(report["template_folder"]).resolve(),
            (APP_DIR / "templates").resolve(),
        )

    def test_entrypoint_guards_the_dashboard_before_serving_data(self):
        report = run_entrypoint_probe()

        self.assertEqual(report["landing_status"], 200)
        self.assertEqual(report["dashboard_status"], 302)
        self.assertEqual(report["dashboard_location"], "/login")


class PackagingConfigTest(unittest.TestCase):
    def test_vercel_json_targets_the_entrypoint(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        functions = config["functions"]
        self.assertIn("wsgi.py", functions)
        self.assertEqual(functions["wsgi.py"]["maxDuration"], 300)

        rules = []
        for pattern in expand_braces(functions["wsgi.py"]["excludeFiles"]):
            rules.append(pattern)
        for path in runtime_files():
            self.assertFalse(
                is_ignored(path, rules), f"{path} is excluded from the function bundle"
            )
        for path in BUILD_ARTIFACTS:
            self.assertTrue(
                is_ignored(path, rules), f"{path} is bundled with the function"
            )

    def test_vercelignore_keeps_runtime_files_and_drops_secrets(self):
        rules = (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
        for path in runtime_files():
            self.assertFalse(
                is_ignored(path, rules), f"{path} is not uploaded to Vercel"
            )
        for path in BUILD_ARTIFACTS:
            self.assertTrue(is_ignored(path, rules), f"{path} is uploaded to Vercel")
        for secret in (".env", ".env.local", "gcp-key.json"):
            self.assertTrue(
                is_ignored(secret, rules), f"{secret} is uploaded to Vercel"
            )


class RuntimeDependencyTest(unittest.TestCase):
    def test_runtime_dependencies_cover_every_app_import(self):
        declared = _project_requirements()
        distributions = importlib.metadata.packages_distributions()
        for module in sorted(reachable_imports()):
            if module in sys.stdlib_module_names:
                continue
            providers = distributions.get(module, [])
            self.assertTrue(
                providers,
                f"{module} is imported by the app but is not provided by any package",
            )
            self.assertTrue(
                any(
                    provider.lower().replace("_", "-") in declared
                    for provider in providers
                ),
                f"{module} ({', '.join(providers)}) is not a runtime dependency",
            )

    def test_app_starts_without_the_build_dependencies(self):
        """The deployment must not need a package that only the build uses."""
        blocked = modules_without_runtime_provider()
        self.assertTrue(
            blocked,
            "no build-only package was detected; the deployment guard is inert",
        )
        self.assertTrue(
            set(KNOWN_BUILD_ONLY_MODULES) & blocked,
            "the known build-only packages are missing from the blocked set; "
            "install the dev group so the guard has something to block",
        )
        report = run_entrypoint_probe(blocked=blocked)
        self.assertEqual(report["landing_status"], 200)
        self.assertEqual(report["dashboard_status"], 302)

    @unittest.skipUnless(shutil.which("uv"), "uv is required to export the lock file")
    def test_requirements_match_the_locked_runtime_export(self):
        with tempfile.TemporaryDirectory() as directory:
            exported = Path(directory) / "requirements.txt"
            subprocess.run(
                [
                    "uv",
                    "export",
                    "--frozen",
                    "--no-dev",
                    "--no-emit-project",
                    "--no-header",
                    "--format",
                    "requirements-txt",
                    "--output-file",
                    str(exported),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(
                _pinned_packages(exported),
                _pinned_packages(ROOT / "requirements.txt"),
                "requirements.txt drifted from the locked runtime dependencies",
            )


def _project_requirements():
    """Return the runtime dependency names declared in pyproject.toml."""
    content = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    start = content.index("dependencies = [")
    end = content.index("]", start)
    names = set()
    for line in content[start:end].splitlines():
        match = re.match(r'\s*"([A-Za-z0-9._-]+)', line)
        if match:
            names.add(match.group(1).lower().replace("_", "-"))
    return names


def _pinned_packages(path):
    """Return the name and version of every pinned requirement in a file."""
    pinned = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith((" ", "#", "-")):
            continue
        if "==" in line:
            name, _, version = line.partition("==")
            pinned.add((name.strip().lower(), version.strip().split()[0]))
    return pinned


if __name__ == "__main__":
    unittest.main()
