"""The platform seams: directory policy and credential resolution.

These are the abstractions that let the same code run on macOS and
Linux, and they are testable on either — which is the point of
building the seam before the second backend. A resolver with a
platform override can be exercised on a Mac; an env-backed credential
path needs no keyring at all.

The directory policy has exactly one implementation, ``app_path`` in
``cli/sc``; the shell helpers and the Node connectors call
``sc paths <kind>`` rather than reimplementing it. So these tests
exercise the policy once, and then check that the callers really do
delegate — a copy that agrees today is still a copy, and a test
asserting two copies agree is a weaker guarantee than not having two
copies.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB_SH = REPO_ROOT / "sync" / "lib.sh"
CORE = REPO_ROOT / "connectors" / "core"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)

# A fixed HOME so both implementations are compared against the same
# base, and so a developer's real XDG settings can't leak in.
BASE_ENV = {
    "HOME": "/home/testuser",
    "PATH": os.environ.get("PATH", ""),
}


def _node(expr: str, env: dict[str, str]) -> str:
    """Evaluate a JS expression against connectors/core, return stdout."""
    out = subprocess.run(
        ["node", "-e", f'process.stdout.write(String({expr}))'],
        cwd=CORE,
        env={**BASE_ENV, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _sh_log_root(env: dict[str, str]) -> str:
    out = subprocess.run(
        ["sh", "-c", f'. "{LIB_SH}"; sc_log_root'],
        env={**BASE_ENV, "PROSAIC_ROOT": str(REPO_ROOT), **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _js_log_dir(env: dict[str, str]) -> str:
    return _node("require('./paths').logDir()", env)


# --- directory policy -------------------------------------------------


SC = REPO_ROOT / "cli" / "sc"


def _sc_paths(kind: str, env: dict[str, str]) -> str:
    out = subprocess.run(
        [str(SC), "paths", kind],
        env={**BASE_ENV, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


@pytest.mark.parametrize(
    "kind,env,expected",
    [
        # macOS keeps its existing locations: this is a seam, not a move.
        ("log-dir", {"PROSAIC_PLATFORM": "darwin"},
         "/home/testuser/Library/Logs/prosaic"),
        ("cache-dir", {"PROSAIC_PLATFORM": "darwin"},
         "/home/testuser/Library/Caches/prosaic"),
        # Linux without XDG set falls back to the spec's defaults.
        ("log-dir", {"PROSAIC_PLATFORM": "linux"},
         "/home/testuser/.local/state/prosaic/logs"),
        ("cache-dir", {"PROSAIC_PLATFORM": "linux"},
         "/home/testuser/.cache/prosaic"),
        # XDG honored when absolute.
        ("log-dir", {"PROSAIC_PLATFORM": "linux", "XDG_STATE_HOME": "/var/lib/state"},
         "/var/lib/state/prosaic/logs"),
        # XDG says a relative value is invalid and must be ignored —
        # resolving it against the cwd would scatter logs wherever the
        # process happened to start.
        ("log-dir", {"PROSAIC_PLATFORM": "linux", "XDG_STATE_HOME": "relative/path"},
         "/home/testuser/.local/state/prosaic/logs"),
        # The explicit override beats everything, on every platform.
        ("log-dir", {"PROSAIC_PLATFORM": "darwin", "PROSAIC_LOG_DIR": "/tmp/sclogs"},
         "/tmp/sclogs"),
        ("log-dir", {"PROSAIC_PLATFORM": "linux", "PROSAIC_LOG_DIR": "/tmp/sclogs"},
         "/tmp/sclogs"),
        # Browser profiles live under data-dir; relocating it on macOS
        # would silently invalidate live portal sessions, so it is
        # pinned to the XDG location on both platforms until a
        # migration exists.
        ("data-dir", {"PROSAIC_PLATFORM": "darwin"},
         "/home/testuser/.local/share/prosaic"),
        ("data-dir", {"PROSAIC_PLATFORM": "linux"},
         "/home/testuser/.local/share/prosaic"),
    ],
)
def test_directory_policy(kind, env, expected) -> None:
    """The one implementation, exercised directly."""
    assert _sc_paths(kind, env) == expected


@pytest.mark.parametrize("kind", ["log-dir", "data-dir", "cache-dir"])
@pytest.mark.parametrize("plat", ["darwin", "linux"])
def test_node_delegates_rather_than_reimplementing(kind, plat) -> None:
    """paths.js must return what `sc paths` says — because it asked it.

    This is a delegation check, not an agreement check: there is no
    second implementation for it to agree with. If someone reintroduces
    one and it drifts, this fails; if they reintroduce one that happens
    to match, the shape of paths.js is the thing to review.
    """
    env = {"PROSAIC_PLATFORM": plat}
    camel = {"log-dir": "logDir", "data-dir": "dataDir", "cache-dir": "cacheDir"}[kind]
    assert _node(f"require('./paths').{camel}()", env) == _sc_paths(kind, env)


def test_shell_delegates_rather_than_reimplementing() -> None:
    env = {"PROSAIC_PLATFORM": "linux"}
    assert _sh_log_root(env) == _sc_paths("log-dir", env)


def test_inherited_env_short_circuits_the_subprocess() -> None:
    """The hot path spawns nothing.

    matter_sync.sh resolves once and exports; every connector it starts
    must take the inherited value without shelling out again. Proved by
    booby-trapping execFileSync before paths.js captures it: if the
    module tries to spawn, the call raises instead of returning.
    """
    proc = subprocess.run(
        [
            "node",
            "-e",
            "require('child_process').execFileSync = () => { throw new Error('SPAWNED'); };"
            "process.stdout.write(require('./paths').logDir());",
        ],
        cwd=CORE,
        env={**BASE_ENV, "PROSAIC_LOG_DIR": "/tmp/inherited"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"spawned a subprocess it did not need: {proc.stderr}"
    assert proc.stdout.strip() == "/tmp/inherited"


# --- credential resolution --------------------------------------------


def test_env_backend_resolves_and_slugifies() -> None:
    env = {
        "PROSAIC_SECRET_BACKEND": "env",
        "PROSAIC_MYCASE_USERNAME": "someone@example.com",
        "PROSAIC_MYCASE_PASSWORD": "hunter2",
    }
    got = _node(
        "JSON.stringify(require('./secrets')"
        ".resolveCredential('prosaic.mycase'))",
        env,
    )
    assert json.loads(got) == {
        "account": "someone@example.com",
        "password": "hunter2",
    }


def test_env_backend_wins_over_keychain_under_auto() -> None:
    """So a headless run or a test account can override without
    touching the developer's keyring."""
    env = {
        "PROSAIC_PLATFORM": "darwin",
        "PROSAIC_MYCASE_USERNAME": "env-account",
        "PROSAIC_MYCASE_PASSWORD": "env-secret",
    }
    got = json.loads(
        _node(
            "JSON.stringify(require('./secrets')"
            ".resolveCredential('prosaic.mycase'))",
            env,
        )
    )
    assert got["account"] == "env-account"


def test_half_configured_env_is_an_error_not_a_fallthrough() -> None:
    """A username with no password means someone made a mistake; falling
    through to another backend would hide it."""
    proc = subprocess.run(
        [
            "node",
            "-e",
            "require('./secrets').resolveCredential('prosaic.mycase')",
        ],
        cwd=CORE,
        env={
            **BASE_ENV,
            "PROSAIC_PLATFORM": "linux",
            "PROSAIC_MYCASE_USERNAME": "someone@example.com",
        },
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "half-configured" in proc.stderr


def test_unsupported_platform_names_the_env_vars_to_set() -> None:
    """An error a user can act on beats a stack trace."""
    proc = subprocess.run(
        ["node", "-e", "require('./secrets').resolveCredential('prosaic.mycase')"],
        cwd=CORE,
        env={**BASE_ENV, "PROSAIC_PLATFORM": "linux"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "PROSAIC_MYCASE_USERNAME" in proc.stderr
    assert "PROSAIC_MYCASE_PASSWORD" in proc.stderr


@pytest.mark.parametrize(
    "cfg,expected",
    [
        ('{credential: "a.b"}', "a.b"),
        ('{keychain_service: "old.name"}', "old.name"),  # deprecated alias
        ('{credential: "new", keychain_service: "old"}', "new"),  # new wins
        ("{}", "fallback.default"),
        ("null", "fallback.default"),
    ],
)
def test_credential_ref_accepts_the_deprecated_key(cfg, expected) -> None:
    """Matters in flight must not break on the rename."""
    got = _node(
        f"require('./secrets').credentialRef({cfg}, 'fallback.default')",
        {},
    )
    assert got == expected


def test_deprecated_key_warns_so_the_alias_does_not_become_permanent() -> None:
    proc = subprocess.run(
        [
            "node",
            "-e",
            "require('./secrets').credentialRef({keychain_service: 'x'}, 'y')",
        ],
        cwd=CORE,
        env=BASE_ENV,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "deprecated" in proc.stderr.lower()
