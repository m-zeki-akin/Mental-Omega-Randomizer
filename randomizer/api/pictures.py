"""Getting a picture to a page that is not allowed to open files.

A page loaded from a file cannot open another file: the engine refuses
it, and a refused picture looks exactly like a thing that has none. So
the bytes go across the bridge with the answer they belong to, and the
page keeps them.

Two kinds of picture go this way and they are not the same size. A map
preview is a few hundred kilobytes and there are three of them on a
screen. A cameo is under four, and a list may want two hundred. So the
ceiling is the caller's to say -- one number here for both would be
either too mean for a map or far too generous for an icon.
"""

import base64
from pathlib import Path


def data_uri(path, *, ceiling):
    """Return one picture as data, or nothing at all.

    Nothing rather than an error: a picture that cannot be read is a row
    without an icon, which is a thing a screen can draw. Refusing the
    whole answer over it would not be.
    """
    if not path:
        return ''
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size > ceiling:
            return ''
        raw = path.read_bytes()
    except OSError:
        return ''
    return f'data:image/png;base64,{base64.b64encode(raw).decode("ascii")}'
