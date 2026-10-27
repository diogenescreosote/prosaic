"""The gmail token files: a refresh_token is never lost.

Google sends a refresh_token only at consent. A token file that loses
it works until the access token expires an hour later, and then every
pull fails with invalid_grant until someone re-authorizes. These tests
pin the two writers (auth.js's save and the OAuth client's refresh
handler) to merging into the file as it is on disk, and the primary
account's own file and credentials.json to staying in step.

Every token here is a made-up string; nothing touches Google.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GMAIL = REPO_ROOT / "connectors" / "gmail"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

KEYS = {
    "installed": {
        "client_id": "id.example",
        "client_secret": "not-a-secret",
        "redirect_uris": ["http://localhost"],
    }
}


def _node(body: str, creds_dir: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PROSAIC_GMAIL_CREDS_DIR": str(creds_dir),
        "NODE_PATH": str(REPO_ROOT / "connectors" / "node_modules"),
    }
    proc = subprocess.run(
        ["node", "-e", body], cwd=GMAIL, capture_output=True, text=True, env=env, timeout=60
    )
    assert proc.returncode == 0, f"node failed:\n{proc.stdout}\n{proc.stderr}"
    return proc


def _json(body: str, creds_dir: Path) -> Any:
    return json.loads(_node(body, creds_dir).stdout.strip().splitlines()[-1])


@pytest.fixture
def creds_dir(tmp_path: Path) -> Path:
    d = tmp_path / "creds"
    d.mkdir()
    (d / "oauth-keys.json").write_text(json.dumps(KEYS))
    return d


def _write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data))


def _read(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(path.read_text())
    return result


OWN = "credentials-jane_example_com.json"


def test_a_refresh_never_drops_the_refresh_token(creds_dir: Path) -> None:
    """The refresh event's payload has no refresh_token (or an empty one);
    the file keeps the one it had, and the alias is brought into step."""
    _write(creds_dir / OWN, {"access_token": "a0", "refresh_token": "r-jane", "expiry_date": 1})
    _write(creds_dir / "credentials.json", {"access_token": "old", "expiry_date": 1})
    _node(
        """
        const creds = require('./creds');
        const auth = creds.loadOAuthClient('jane@example.com', { primary: true });
        auth.emit('tokens', { access_token: 'a1', expiry_date: 2, refresh_token: undefined });
        auth.emit('tokens', { access_token: 'a2', expiry_date: 3, refresh_token: null });
        """,
        creds_dir,
    )
    own = _read(creds_dir / OWN)
    legacy = _read(creds_dir / "credentials.json")
    assert own["refresh_token"] == "r-jane" and own["access_token"] == "a2"
    assert legacy["refresh_token"] == "r-jane", "credentials.json no longer diverges"
    assert legacy["access_token"] == "a2"
    assert ((creds_dir / OWN).stat().st_mode & 0o777) == 0o600


def test_a_refresh_merges_into_the_file_as_it_is_now(creds_dir: Path) -> None:
    """A run that loaded its token before a re-authorization must not
    write its stale copy over the new one."""
    _write(creds_dir / "credentials.json", {"access_token": "a0", "refresh_token": "r-old"})
    _node(
        """
        const fs = require('fs'); const path = require('path');
        const creds = require('./creds');
        const auth = creds.loadOAuthClient(null);
        // auth.js runs while this process is still going
        fs.writeFileSync(path.join(process.env.PROSAIC_GMAIL_CREDS_DIR, 'credentials.json'),
          JSON.stringify({ access_token: 'fresh', refresh_token: 'r-new', account: 'jane@example.com' }));
        auth.emit('tokens', { access_token: 'stale-refresh', expiry_date: 9 });
        """,
        creds_dir,
    )
    t = _read(creds_dir / "credentials.json")
    assert t["refresh_token"] == "r-new" and t["access_token"] == "fresh"
    assert t["account"] == "jane@example.com"


def test_a_file_that_lost_its_refresh_token_gets_it_back(creds_dir: Path) -> None:
    _write(creds_dir / "credentials.json", {"access_token": "a0", "refresh_token": "r1"})
    _node(
        """
        const fs = require('fs'); const path = require('path');
        const creds = require('./creds');
        const auth = creds.loadOAuthClient(null);
        fs.writeFileSync(path.join(process.env.PROSAIC_GMAIL_CREDS_DIR, 'credentials.json'),
          JSON.stringify({ access_token: 'x' }));
        auth.emit('tokens', { access_token: 'a1' });
        """,
        creds_dir,
    )
    assert _read(creds_dir / "credentials.json")["refresh_token"] == "r1"


def test_consent_without_a_refresh_token_keeps_the_saved_one(creds_dir: Path) -> None:
    _write(creds_dir / OWN, {"refresh_token": "r-jane", "account": "jane@example.com"})
    _write(
        creds_dir / "credentials.json", {"refresh_token": "r-legacy", "account": "jane@example.com"}
    )
    out = _json(
        """
        const path = require('path');
        const creds = require('./creds');
        const dir = process.env.PROSAIC_GMAIL_CREDS_DIR;
        const written = creds.saveAuthorized(path.join(dir, 'credentials-jane_example_com.json'),
          { access_token: 'a-new', expiry_date: 5 }, 'jane@example.com');
        const other = creds.saveAuthorized(path.join(dir, 'credentials-service_example_com.json'),
          { access_token: 's', refresh_token: 'r-service' }, 'service@example.com');
        console.log(JSON.stringify({ written: written.map((f) => path.basename(f)),
          other: other.map((f) => path.basename(f)) }));
        """,
        creds_dir,
    )
    assert out["written"] == [OWN, "credentials.json"]
    assert out["other"] == ["credentials-service_example_com.json"], (
        "another mailbox's consent never touches credentials.json"
    )
    own = _read(creds_dir / OWN)
    assert own["refresh_token"] == "r-jane" and own["access_token"] == "a-new"
    assert own["account"] == "jane@example.com"
    assert _read(creds_dir / "credentials.json")["access_token"] == "a-new"


def test_the_primary_reads_whichever_name_still_has_a_refresh_token(creds_dir: Path) -> None:
    _write(creds_dir / OWN, {"access_token": "a"})
    _write(creds_dir / "credentials.json", {"refresh_token": "r"})
    body = """
        const path = require('path'); const creds = require('./creds');
        console.log(JSON.stringify({
          primary: path.basename(creds.tokenPath('jane@example.com', { primary: true })),
          second: path.basename(creds.tokenPath('jane@example.com', { primary: false })),
        }));
    """
    assert _json(body, creds_dir) == {"primary": "credentials.json", "second": OWN}
    # recorded as a different mailbox, credentials.json is no alias
    _write(creds_dir / "credentials.json", {"refresh_token": "r", "account": "other@example.com"})
    assert _json(body, creds_dir)["primary"] == OWN


def test_a_missing_refresh_token_is_named_but_no_token_is_printed(creds_dir: Path) -> None:
    _write(creds_dir / "credentials.json", {"access_token": "SECRET-ACCESS-VALUE"})
    proc = _node("require('./creds').loadOAuthClient(null);", creds_dir)
    assert "has no refresh_token" in proc.stderr
    assert "SECRET-ACCESS-VALUE" not in proc.stderr + proc.stdout
