"""One durable anonymous owner for every configured EasIFA endpoint."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile

from .config import EasifaMCPSettings

_TOKEN = re.compile(r'^[A-Za-z0-9_-]{43,128}$')


def _validate(value: object) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError('Invalid EasIFA owner key; use a saved key or a securely generated 32-byte token.')
    return value


def _read(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'r', encoding='utf-8') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 8192:
            raise ValueError('Invalid EasIFA owner file; expected a small regular recovery file.')
        if os.name == 'posix' and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise ValueError('EasIFA owner file must belong to the current user with permissions 0600.')
        data = json.load(handle)
    if not isinstance(data, dict) or data.get('format') != 'easifa-access' or data.get('version') != 1:
        raise ValueError('Invalid EasIFA recovery file format.')
    return _validate(data.get('token'))


def load_owner_key(settings: EasifaMCPSettings) -> str:
    if settings.session_key is not None:
        return _validate(settings.session_key)
    path = settings.owner_file()
    try:
        return _read(path)
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        raise RuntimeError('Cannot read the saved EasIFA identity. Preserve the file and check its format/permissions, or set EASIFA_SESSION_KEY.') from None

    # Publish a complete file atomically without replacing an existing identity.
    # Concurrent MCP processes therefore converge on the first saved key.
    temporary = None
    try:
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.session-', dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump({'format': 'easifa-access', 'version': 1, 'token': secrets.token_urlsafe(32)}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        return _read(path)
    except (OSError, ValueError):
        # Never continue with an ephemeral identity that would orphan new tasks.
        raise RuntimeError('Cannot persist the EasIFA identity. Set a writable EASIFA_MCP_SESSION_FILE or a persistent EASIFA_SESSION_KEY before submitting jobs.') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
