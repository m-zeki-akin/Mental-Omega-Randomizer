"""Writing into the map a battle is about to be played on.

The client merges a game mode's INI into the map rather than appending it:
the engine keeps the first value it reads for a key, so a section added
underneath the map's own would change nothing. Buying an upgrade writes into
the same file the same way, which is how a purchase reaches a battle.
"""

from pathlib import Path
import re


def _sections(text):
    parts = re.split(r'^\[(.+?)\]\s*$', text, flags=re.M)
    return {
        name.strip(): body
        for name, body in zip(parts[1::2], parts[2::2])
    }


def _values(body):
    values = {}
    for line in (body or '').splitlines():
        line = line.split(';', 1)[0].strip()
        if '=' not in line or line.startswith('['):
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip()
    return values


def merge_into_map(map_path, sections):
    """Apply ``{section: {key: value}}`` to a map already copied into place.

    A key the caller names replaces the map's, and a section the map does
    not have is added at the end. Appending instead would leave the map's
    own value first, and the reader keeps the first it sees -- which is
    exactly the value the caller meant to change.
    """
    map_path = Path(map_path)
    code = {
        name: values for name, values in (sections or {}).items() if values
    }
    if not code:
        return 0
    original = map_path.read_bytes().decode('utf-8', errors='ignore')
    # These maps are written with bare line feeds. Rewriting them as CRLF
    # would change every line of a file the merge has no business reshaping.
    newline = '\r\n' if '\r\n' in original else '\n'
    lines = original.splitlines()
    # Where each section starts and ends, in the order the map has them.
    bounds = {}
    current = None
    start = 0
    for index, line in enumerate(lines):
        header = re.match(r'^\[(.+?)\]\s*$', line.strip())
        if not header:
            continue
        if current is not None:
            bounds.setdefault(current, (start, index))
        current = header.group(1).strip()
        start = index + 1
    if current is not None:
        bounds.setdefault(current, (start, len(lines)))

    applied = 0
    additions = []
    # Rewritten from the bottom up so earlier line numbers stay valid.
    for section in sorted(
        code, key=lambda name: bounds.get(name, (len(lines), 0))[0],
        reverse=True,
    ):
        values = code[section]
        if section not in bounds:
            additions.append((section, values))
            continue
        begin, end = bounds[section]
        body = lines[begin:end]
        for key, value in values.items():
            replaced = False
            for offset, line in enumerate(body):
                stripped = line.split(';', 1)[0].strip()
                if '=' not in stripped:
                    continue
                if stripped.split('=', 1)[0].strip().lower() == key.lower():
                    body[offset] = f'{key}={value}'
                    replaced = True
                    break
            if not replaced:
                body.append(f'{key}={value}')
            applied += 1
        lines[begin:end] = body
    for section, values in reversed(additions):
        lines.append('')
        lines.append(f'[{section}]')
        for key, value in values.items():
            lines.append(f'{key}={value}')
            applied += 1
    with open(map_path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(newline.join(lines) + newline)
    return applied
