"""Small persistence helpers shared by config and active seed state."""

import gzip
import json
import os
import threading
from pathlib import Path

# Marks a file whose JSON is compressed rather than written out in the clear.
# Version byte included so a later format change is a readable failure rather
# than a decompression error.
OPAQUE_MAGIC = b'MORP' + bytes([1])


def atomic_write_text(path, text, encoding='utf-8'):
    """Replace a text file only after its complete new content reaches disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(
        f'.{path.name}.{os.getpid()}.{threading.get_ident()}.tmp'
    )
    try:
        temporary_path.write_text(text, encoding=encoding)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def read_json_object(path):
    """Read one required JSON object; let caller decide recovery/logging."""
    path = Path(path)
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError(f'JSON root must be an object: {path}')
    return data


def atomic_write_json(path, data, *, indent=2):
    """Serialize an object consistently through atomic text replacement."""
    options = {'indent': indent}
    if indent is None:
        options['separators'] = (',', ':')
    atomic_write_text(path, json.dumps(data, **options))


def atomic_write_bytes(path, data):
    """Replace a binary file only after its complete new content reaches disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(
        f'.{path.name}.{os.getpid()}.{threading.get_ident()}.tmp'
    )
    try:
        temporary_path.write_bytes(data)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write_opaque(path, data):
    """Write one object as a compressed blob instead of readable JSON.

    This is a doorstep, not protection, and the distinction matters: the same
    bytes are one gzip call from being readable again, and the launcher is on
    the player's own machine. What it stops is the edit that needs no tools at
    all -- opening the file and typing a bigger number. Anything past that was
    never in reach offline, and the signature in the document is what actually
    reports tampering.

    mtime is left out of the gzip header so writing the same state twice
    produces the same bytes.
    """
    payload = json.dumps(data, separators=(',', ':')).encode('utf-8')
    atomic_write_bytes(path, OPAQUE_MAGIC + gzip.compress(payload, mtime=0))


def read_opaque_object(path):
    """Read one object written either as a blob or as plain JSON.

    Plain JSON is still accepted because every profile written before this
    existed is plain JSON, and a player who upgrades has one. It converts on
    the next write.
    """
    path = Path(path)
    raw = path.read_bytes()
    if not raw.startswith(OPAQUE_MAGIC):
        return read_json_object(path)
    data = json.loads(gzip.decompress(raw[len(OPAQUE_MAGIC):]).decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'Stored root must be an object: {path}')
    return data
