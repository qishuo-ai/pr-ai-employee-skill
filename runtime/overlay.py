"""Client-scoped synthetic overlay loading with pre-read authorization."""
import json
import os
import stat
from pathlib import Path

from .schemas import IDENTIFIER, OVERLAY_SCHEMA, validate


class IsolationError(PermissionError):
    pass


def load_overlay(root, *, authorized_clients, session_client, requested_client,
                 document="facts.json"):
    # Authorize and validate before resolving/opening any client path.
    validate(session_client, IDENTIFIER)
    validate(requested_client, IDENTIFIER)
    if requested_client != session_client or session_client not in authorized_clients:
        raise IsolationError("client scope denied")
    if document != "facts.json":
        raise IsolationError("document not allowlisted")
    root = Path(root)
    # O_NOFOLLOW + dir_fd prevent client/document symlink swaps during open.
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise IsolationError("secure directory opens unsupported")
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise IsolationError("overlay root symlink denied")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        client_fd = os.open(requested_client, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=root_fd)
        try:
            fd = os.open(document, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=client_fd)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise IsolationError("overlay must be a regular file")
                data = stream.read(65537)
            if len(data) > 65536:
                raise IsolationError("overlay too large")
        finally:
            os.close(client_fd)
    finally:
        os.close(root_fd)
    overlay = json.loads(data)
    validate(overlay, OVERLAY_SCHEMA)
    if overlay["client_id"] != session_client:
        raise IsolationError("overlay client label mismatch")
    return overlay
