"""Check an installation against the shipped manifest, cheaply enough to run.

The manifest describes 1.3 GB in 59 KB. Verifying it honestly means reading
every file it names, which on a cold disk is around forty seconds -- fine once,
impossible on every start. So almost nothing is read twice:

* A file is re-hashed only when its size or modification time has moved. Both
  come from one ``stat`` call, and 487 of those cost about 20 ms.
* Archive members are re-extracted only when an archive itself has moved, on
  the same reasoning, using the same signature the cameo cache already keys on.

That leaves a first run that pays for the cold read and later runs that pay
for a directory scan: measured at 0.54 s and 0.01 s against a real install.

Be clear about what the fast path costs, because it is a real hole and not a
theoretical one: a matching size and modification time means the cached digest
is **trusted without reading the file**. An edit that preserves both -- which
is exactly what someone deliberately tampering would do -- is missed until
something else moves. ``force=True`` reads everything and catches it; that is
the mode for an explicit check rather than a startup one.

What none of this does is prove an installation is honest. A player who can
edit a file can edit this cache, and the manifest sits inside an executable
they own. It reports what differs from a known-good tree -- a diagnostic that
a mod, a patch, an interrupted download and a failing disk all land in, and
which says nothing about intent.
"""

import json
import time
from hashlib import sha256
from pathlib import Path

from randomizer.core.paths import APP_DIR, GAME_ROOT, SOURCE_DIR

MANIFEST_PATH = SOURCE_DIR / 'configs' / 'authenticity_manifest.json'
CACHE_PATH = APP_DIR / 'authenticity_cache.json'

# Hashed with line endings normalised, for the reason the manifest builder
# gives: the same INI reaches us CRLF from one source and LF from another.
TEXT_SUFFIXES = frozenset({'.ini', '.txt', '.csv'})


def _digest(data, name):
    if Path(name).suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b'\r\n', b'\n')
    return sha256(data).hexdigest()


def load_manifest():
    if not MANIFEST_PATH.is_file():
        return None
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def _load_cache():
    if not CACHE_PATH.is_file():
        return {}
    try:
        cache = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return cache if isinstance(cache, dict) else {}


def _save_cache(cache):
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(cache, separators=(',', ':')), encoding='utf-8'
        )
    except OSError:
        pass


def archive_signature(game_root):
    """Return a stamp of every archive, to decide whether to read them again."""
    parts = []
    for path in sorted(Path(game_root).glob('*.mix')):
        try:
            stat = path.stat()
        except OSError:
            continue
        parts.append(f'{path.name}:{stat.st_size}:{stat.st_mtime_ns}')
    return '|'.join(parts)


def _verify_files(game_root, expected, cached, force):
    """Return per-file results, re-reading only what moved."""
    results = {'clean': 0, 'modified': [], 'missing': []}
    index = {}
    for relative, want in expected.items():
        path = Path(game_root) / relative
        try:
            stat = path.stat()
        except OSError:
            results['missing'].append(relative)
            continue
        stamp = [stat.st_size, stat.st_mtime_ns]
        previous = cached.get(relative)
        if (
            not force and isinstance(previous, list) and len(previous) == 3
            and previous[:2] == stamp
        ):
            digest = previous[2]
        else:
            try:
                digest = _digest(path.read_bytes(), path.name)
            except OSError:
                results['missing'].append(relative)
                continue
        index[relative] = [*stamp, digest]
        if digest == want:
            results['clean'] += 1
        else:
            results['modified'].append(relative)
    return results, index


def _verify_members(game_root, expected):
    """Return per-member results, resolved the way the engine resolves them."""
    import tempfile

    from randomizer.core.mix import extract_mix_members, ordered_mix_paths

    results = {'clean': 0, 'modified': [], 'missing': []}
    digests = {}
    names = sorted(expected)
    archives = ordered_mix_paths(Path(game_root).glob('*.mix'))
    with tempfile.TemporaryDirectory(prefix='mo-authenticity-') as temporary:
        out = Path(temporary)
        try:
            extract_mix_members(
                archives, [(name, out / name.lower()) for name in names]
            )
        except Exception:
            pass
        for name in names:
            path = out / name.lower()
            if not path.is_file():
                results['missing'].append(name)
                continue
            digest = _digest(path.read_bytes(), name)
            digests[name] = digest
            if digest == expected[name]:
                results['clean'] += 1
            else:
                results['modified'].append(name)
    return results, digests


def _member_results_from(digests, expected):
    results = {'clean': 0, 'modified': [], 'missing': []}
    for name, want in expected.items():
        digest = digests.get(name)
        if digest is None:
            results['missing'].append(name)
        elif digest == want:
            results['clean'] += 1
        else:
            results['modified'].append(name)
    return results


def verify_installation(game_root=GAME_ROOT, *, force=False):
    """Return what differs between this installation and the manifest."""
    manifest = load_manifest()
    if manifest is None:
        return {
            'available': False,
            'reason': f'No manifest at {MANIFEST_PATH}',
        }
    started = time.perf_counter()
    cache = {} if force else _load_cache()
    signature = archive_signature(game_root)

    files, index = _verify_files(
        game_root, manifest.get('files') or {},
        cache.get('files') or {}, force,
    )

    expected_members = manifest.get('members') or {}
    cached_digests = cache.get('member_digests') or {}
    reuse = (
        not force
        and cache.get('signature') == signature
        and set(cached_digests) >= set(expected_members)
    )
    if reuse:
        members = _member_results_from(cached_digests, expected_members)
        member_digests = cached_digests
    else:
        members, member_digests = _verify_members(game_root, expected_members)

    report = {
        'available': True,
        'manifest_version': manifest.get('manifest_version'),
        'files_checked': len(manifest.get('files') or {}),
        'files_clean': files['clean'],
        'files_modified': sorted(files['modified']),
        'files_missing': sorted(files['missing']),
        'members_checked': len(expected_members),
        'members_clean': members['clean'],
        'members_modified': sorted(members['modified']),
        'members_missing': sorted(members['missing']),
        'members_from_cache': reuse,
        'elapsed_seconds': round(time.perf_counter() - started, 3),
    }
    report['modified_count'] = (
        len(report['files_modified']) + len(report['members_modified'])
    )
    report['missing_count'] = (
        len(report['files_missing']) + len(report['members_missing'])
    )
    report['stock'] = not (report['modified_count'] or report['missing_count'])
    _save_cache({
        'manifest_version': manifest.get('manifest_version'),
        'signature': signature,
        'files': index,
        'member_digests': member_digests,
    })
    return report


def summary_line(report):
    """Return one line a player can read, or '' when there is nothing to say."""
    if not report.get('available'):
        return ''
    if report.get('stock'):
        return 'Game files: stock'
    parts = []
    if report.get('modified_count'):
        parts.append(f'{report["modified_count"]} modified')
    if report.get('missing_count'):
        parts.append(f'{report["missing_count"]} missing')
    return 'Game files: ' + ', '.join(parts)


def validate_authenticity_contract():
    """Prove the checker reports differences rather than assuming agreement.

    A verifier that never disagrees looks exactly like a clean installation
    from the outside, which is the failure worth guarding against. Every claim
    below is therefore made against a tree built to break it.
    """
    import os
    import tempfile

    with tempfile.TemporaryDirectory(prefix='mo-authenticity-check-') as folder:
        root = Path(folder)
        (root / 'INI').mkdir()
        (root / 'INI' / 'a.ini').write_bytes(b'x=1\r\ny=2\r\n')
        (root / 'data.bin').write_bytes(b'\x00\x01\x02')
        expected = {
            # Written CRLF, hashed LF: the same file reaching us from another
            # source must not read as a different file.
            'INI/a.ini': _digest(b'x=1\ny=2\n', 'a.ini'),
            'data.bin': _digest(b'\x00\x01\x02', 'data.bin'),
        }
        clean, index = _verify_files(root, expected, {}, False)
        cached, _ = _verify_files(root, expected, index, False)

        (root / 'data.bin').write_bytes(b'\x00\x01\x09')
        edited, _ = _verify_files(root, expected, index, False)

        # Same size, same modification time, different content -- and the
        # cache holding a digest that was correct when it was taken, which is
        # what makes the substitution invisible.
        (root / 'data.bin').write_bytes(b'\x00\x01\x02')
        _, disguised_index = _verify_files(root, expected, {}, True)
        stamp = (root / 'data.bin').stat()
        (root / 'data.bin').write_bytes(b'\x00\x01\x0b')
        os.utime(root / 'data.bin', ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        disguised = _verify_files(root, expected, disguised_index, False)[0]
        forced = _verify_files(root, expected, disguised_index, True)[0]

        (root / 'data.bin').unlink()
        deleted, _ = _verify_files(root, expected, index, False)

    return {
        'authenticity_line_endings_valid': clean['clean'] == 2,
        'authenticity_cache_reuse_valid': cached['clean'] == 2,
        'authenticity_edit_detected_valid': edited['modified'] == ['data.bin'],
        'authenticity_missing_detected_valid': (
            deleted['missing'] == ['data.bin']
        ),
        # The documented hole, asserted rather than hoped about: preserving
        # size and modification time defeats the cached path, and only a
        # forced read sees it. Should this ever stop holding, the fast path
        # is no longer being taken and the timings above are fiction.
        'authenticity_stamp_disguise_known_valid': (
            not disguised['modified'] and forced['modified'] == ['data.bin']
        ),
    }
