"""Hold what the stock Mental Omega rules are, without holding the rules.

The launcher builds every player clone from the rules the installation
actually loads, so a submod reaches the game intact. That leaves one question
it still has to answer: *is this section stock?* -- for the modified marker in
the UI, and so the check does not depend on the player keeping an honest copy
of the original files around.

Shipping the originals would answer it and cost 4.2 MB, and worse, the answer
would live in a file the player can edit. So what ships is a digest: one
truncated keyed hash per section, of every section in all four stock INIs.
That is enough to say "this section differs from stock" and not enough to
reconstruct a single line of it.

The hash is keyed rather than plain, for the same reason the shop state is
signed: a plain SHA lets anyone recompute their own edit's digest and patch it
into the table. **This is a doorstep, not a lock** -- the key comes out of the
bundle for anyone who looks, exactly as ``integrity`` says of its own. It stops
the edit that takes ten seconds, which is nearly all of them.

Only ``rulesmo`` (and ``artmo``, for clone art) drives anything today. ``aimo``
and ``battlemo`` are digested because they are part of what "stock" means and
the marginal cost is a few kilobytes; a future check can use them without a
new format.
"""

import base64
import gzip
import hmac
import json
from hashlib import sha256
from pathlib import Path

from randomizer.core.paths import SOURCE_DIR

DIGEST_VERSION = 1
DIGEST_PATH = SOURCE_DIR / 'configs' / 'rules_digest.json'

# Distinct from the shop-state key on purpose: one leaking must not let the
# other be forged.
_KEY = b'mental-omega-randomizer/rules-digest/v1'

# 48 bits per section. With 11,707 sections the chance that an edited section
# collides with its own stock digest is about 2^-48, and the table is a third
# of the size a full hash would make it.
DIGEST_BYTES = 6

MAGIC = b'MORD'

# The four stock INIs, by the short name callers use.
RULES = 'rulesmo'
ART = 'artmo'
AI = 'aimo'
BATTLE = 'battlemo'
FILES = (RULES, ART, AI, BATTLE)

# What one section turned out to be.
ORIGINAL = 'original'  # matches the stock digest
MODIFIED = 'modified'  # present in stock, different here
UNKNOWN = 'unknown'    # not in stock at all: a submod addition


def canonical_section(values):
    """Return the bytes a section's digest covers.

    Keys are compared case-insensitively because the engine reads them that
    way, and sorted because INI key order carries no meaning. Values keep
    their case; ``Image=RAZGAR`` and ``Image=razgar`` name different art.
    """
    items = sorted(
        (str(key).strip().lower(), str(value).strip())
        for key, value in dict(values).items()
    )
    return '\n'.join('{}={}'.format(key, value) for key, value in items).encode(
        'utf-8'
    )


def section_digest(values):
    """Return one section's truncated keyed digest."""
    return hmac.new(
        _KEY, canonical_section(values), sha256
    ).digest()[:DIGEST_BYTES]


def encode_blob(digests):
    """Pack ``{file: {section: digest}}`` into the shipped blob.

    Section names compress; digests do not, so the names are what gzip earns
    its place on.
    """
    parts = [MAGIC, bytes([DIGEST_VERSION])]
    for name in FILES:
        entries = sorted(digests.get(name, {}).items())
        parts.append(name.encode('ascii') + b'\0')
        parts.append(len(entries).to_bytes(4, 'big'))
        for section, digest in entries:
            parts.append(section.encode('utf-8') + b'\0')
            parts.append(bytes(digest))
    packed = gzip.compress(b''.join(parts), mtime=0)
    return base64.b64encode(packed).decode('ascii')


def decode_blob(blob):
    """Return ``{file: {section: digest}}`` from a shipped blob."""
    raw = gzip.decompress(base64.b64decode(blob))
    if not raw.startswith(MAGIC) or raw[len(MAGIC)] != DIGEST_VERSION:
        raise ValueError('Unrecognised rules digest blob.')
    offset = len(MAGIC) + 1
    digests = {}
    while offset < len(raw):
        end = raw.index(b'\0', offset)
        name = raw[offset:end].decode('ascii')
        offset = end + 1
        count = int.from_bytes(raw[offset:offset + 4], 'big')
        offset += 4
        entries = {}
        for _index in range(count):
            end = raw.index(b'\0', offset)
            section = raw[offset:end].decode('utf-8')
            offset = end + 1
            entries[section] = raw[offset:offset + DIGEST_BYTES]
            offset += DIGEST_BYTES
        digests[name] = entries
    return digests


def blob_signature(blob):
    """Return the signature covering a packed blob."""
    return hmac.new(_KEY, blob.encode('ascii'), sha256).hexdigest()


def build_document(digests):
    """Return the shipped JSON document for a set of section digests."""
    blob = encode_blob(digests)
    return {
        'digest_version': DIGEST_VERSION,
        'sections': {name: len(digests.get(name, {})) for name in FILES},
        'blob': blob,
        'signature': blob_signature(blob),
    }


def _load_document(path=None):
    path = Path(path) if path is not None else DIGEST_PATH
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


_CACHE = {}


def load_digests(path=None):
    """Return ``{file: {SECTION: digest}}``, or ``{}`` when unavailable.

    Sections are keyed upper-case: the caller holds an installed section name
    whose case is whatever the mod author typed.
    """
    key = str(path or DIGEST_PATH)
    if key in _CACHE:
        return _CACHE[key]
    document = _load_document(path)
    digests = {}
    blob = (document or {}).get('blob')
    if isinstance(blob, str) and hmac.compare_digest(
        str((document or {}).get('signature') or ''), blob_signature(blob)
    ):
        try:
            digests = {
                name: {
                    section.upper(): digest
                    for section, digest in entries.items()
                }
                for name, entries in decode_blob(blob).items()
            }
        except (ValueError, IndexError, OSError):
            digests = {}
    _CACHE[key] = digests
    return digests


def available(path=None):
    """True when a valid digest table shipped with this build."""
    return bool(load_digests(path))


def section_status(source, section, values, *, path=None):
    """Return ORIGINAL, MODIFIED or UNKNOWN for one installed section."""
    entries = load_digests(path).get(source)
    if not entries:
        return UNKNOWN
    expected = entries.get(str(section).upper())
    if expected is None:
        return UNKNOWN
    return ORIGINAL if section_digest(values) == expected else MODIFIED


def compare_sections(source, sections, *, path=None):
    """Return ``{'original': n, 'modified': [...], 'unknown': [...]}``."""
    modified = []
    unknown = []
    original = 0
    for section, values in dict(sections or {}).items():
        status = section_status(source, section, values, path=path)
        if status == ORIGINAL:
            original += 1
        elif status == MODIFIED:
            modified.append(str(section))
        else:
            unknown.append(str(section))
    return {
        'original': original,
        'modified': sorted(modified),
        'unknown': sorted(unknown),
    }


def summary_line(report, source=RULES):
    """Return one log line describing a comparison against stock."""
    if not report:
        return '{}: stok karsilastirmasi yapilamadi (digest yok).'.format(source)
    return '{}: {} orijinal, {} degistirilmis, {} stokta yok.'.format(
        source,
        report['original'],
        len(report['modified']),
        len(report['unknown']),
    )


def validate_rules_digest_contract():
    """Prove the table answers ORIGINAL, MODIFIED and UNKNOWN differently.

    A digest check that reports everything original is indistinguishable from
    a working one until the day it matters, so every claim here is made
    against a table built to break it.
    """
    import json
    import tempfile

    stock = {
        'E1': {'Cost': '120', 'Strength': '135'},
        'GAHYPE': {'Cost': '2000', 'BuildLimit': '2'},
    }
    digests = {RULES: {name: section_digest(values)
                       for name, values in stock.items()}}
    document = build_document(digests)

    with tempfile.TemporaryDirectory(prefix='mo-rules-digest-') as folder:
        good = Path(folder) / 'digest.json'
        good.write_text(json.dumps(document), encoding='utf-8')
        report = compare_sections(RULES, {
            'E1': {'Cost': '120', 'Strength': '135'},
            # Key case and order carry no meaning to the engine, so they must
            # carry none here either -- otherwise a reformatted stock file
            # reads as a mod.
            'GAHYPE': {'buildlimit': '2', 'cost': '2000'},
            'YURIX2': {'Cost': '1'},
        }, path=good)
        recognised = report == {
            'original': 2, 'modified': [], 'unknown': ['YURIX2'],
        }
        edited = compare_sections(RULES, {
            'E1': {'Cost': '130', 'Strength': '135'},
        }, path=good)

        # The blob is the whole table; a player who edits one digest into it
        # would otherwise make one section stock again.
        tampered_document = dict(document)
        blob = bytearray(base64.b64decode(document['blob']))
        blob[-1] ^= 0xFF
        tampered_document['blob'] = base64.b64encode(bytes(blob)).decode('ascii')
        bad = Path(folder) / 'tampered.json'
        bad.write_text(json.dumps(tampered_document), encoding='utf-8')
        tampered = load_digests(path=bad)

        missing = load_digests(path=Path(folder) / 'absent.json')

    shipped = load_digests()
    declared = (_load_document() or {}).get('sections') or {}
    return {
        'rules_digest_roundtrip_valid': recognised,
        'rules_digest_edit_detected_valid': edited['modified'] == ['E1'],
        # A table that fails to load must answer UNKNOWN, never ORIGINAL: the
        # missing-file case has to be the one that accuses nobody and clears
        # nobody.
        'rules_digest_tamper_rejected_valid': (
            not tampered
            and not missing
            and section_status(RULES, 'E1', stock['E1'], path=Path('absent'))
            == UNKNOWN
        ),
        # And the shipped table is the real one, not a stub that happens to
        # pass everything above.
        'rules_digest_shipped_valid': (
            bool(shipped)
            and len(shipped.get(RULES, {})) > 4000
            and all(
                len(shipped.get(name, {})) == int(declared.get(name, -1))
                for name in FILES
            )
        ),
    }
