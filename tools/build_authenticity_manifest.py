"""Build the manifest an installation is checked against.

Run over a pristine Mental Omega tree; writes a few hundred kilobytes of
hashes that ship with the launcher, so the 1.3 GB the hashes describe does
not have to.

Two kinds of entry, and the distinction is the whole point:

``files`` are hashed as they sit on disk -- the INI tree, MapsMO, the DLLs.

``members`` are hashed *inside* the MIX archives, one entry per member, not
one per archive. Hashing the archives themselves does not work. Mental Omega
ships them protected; a player who unprotects one, which Mix-Unprotect and XCC
both do, gets an archive with the same members in a different container, and
every archive-level hash breaks. Measured on a real installation: every
expandmo archive fails Mental Omega's own ``version`` manifest after
unprotecting, while all four rules INIs inside them are byte-identical. Member
hashes survive the repack because the members are what was repacked.

MIX indexes store hashed names rather than names, so members cannot be
enumerated -- they can only be looked up. The list of names therefore comes
from the pristine tree's own ``configs/maps`` set and the rules INIs, and
anything not named here is not checked.

    python tools/build_authenticity_manifest.py <pristine tree> [output]
"""

import json
import sys
import tempfile
import time
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from randomizer.core.mix import extract_mix_members, ordered_mix_paths  # noqa: E402

MANIFEST_VERSION = 1

# Hashed on disk, by relative path. MapsMO/Standard is left out on purpose:
# 1,440 files and 276 MB of skirmish maps that a campaign randomizer never
# touches, and four fifths of the whole reference tree. The map pool the
# launcher does care about lives in configs/maps and is covered below.
FILE_TREES = (
    'INI', 'Resources', 'MapsMO/Challenge', 'MapsMO/Cooperative',
)
FILE_NAMES = (
    'Ares.dll', 'Ares.dll.inj', 'MentalOmegaClient.exe', 'clientupdt.dat',
    'cncnet5.dll', 'cncnet5mo.dll', 'qres.dat', 'qres32.dll', 'version',
)

# Looked up inside the archives. Rules first, then whatever campaign maps the
# launcher's own map pool names.
MEMBER_INIS = ('RULESMO.INI', 'AIMO.INI', 'ARTMO.INI', 'BATTLEMO.INI')

# Text is hashed with its line endings normalised. The same INI arrives with
# CRLF from one source and LF from another -- on a real installation that is a
# 119 KB difference in a 2.2 MB file, and identical content would fail a raw
# byte hash for no reason at all.
TEXT_SUFFIXES = frozenset({'.ini', '.txt', '.csv'})


def canonical_digest(data, name):
    if Path(name).suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b'\r\n', b'\n')
    return sha256(data).hexdigest()


def campaign_member_names():
    """Return the map members to check, from the launcher's own pool.

    Campaign maps are the ones that live inside the archives; challenge and
    cooperative maps sit loose under MapsMO and are covered as files.
    """
    folder = ROOT / 'configs' / 'maps' / 'campaign'
    return tuple(sorted(path.name.upper() for path in folder.glob('*.map')))


def bundled_ini_digests():
    """Return the four rules INIs from the copies kept beside the launcher.

    configs/*-original.ini hold the same bytes as the archive members -- that
    was checked against the pristine tree before this was written -- and they
    are here rather than a gigabyte away, so a manifest can be rebuilt without
    the reference tree at hand.
    """
    sources = {
        'RULESMO.INI': ROOT / 'configs' / 'rulesmo-original.ini',
        'AIMO.INI': ROOT / 'configs' / 'aimo-original.ini',
        'ARTMO.INI': ROOT / 'configs' / 'artmo-original.ini',
        'BATTLEMO.INI': ROOT / 'configs' / 'maps' / 'battlemo-original.ini',
    }
    return {
        name: canonical_digest(path.read_bytes(), name)
        for name, path in sources.items() if path.is_file()
    }


def hash_files(tree):
    entries = {}
    for name in FILE_NAMES:
        path = tree / name
        if path.is_file():
            entries[name] = canonical_digest(path.read_bytes(), name)
    for folder in FILE_TREES:
        base = tree / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*')):
            if not path.is_file():
                continue
            key = path.relative_to(tree).as_posix()
            entries[key] = canonical_digest(path.read_bytes(), path.name)
    return entries


def hash_members(tree, names):
    """Return member digests, resolved the way the engine resolves them."""
    archives = ordered_mix_paths(tree.glob('*.mix'))
    with tempfile.TemporaryDirectory(prefix='mo-manifest-') as temporary:
        out = Path(temporary)
        extract_mix_members(
            archives, [(name, out / name.lower()) for name in names]
        )
        entries = {}
        missing = []
        for name in names:
            path = out / name.lower()
            if path.is_file():
                entries[name] = canonical_digest(path.read_bytes(), name)
            else:
                missing.append(name)
    return entries, missing, [path.name for path in archives]


def build(tree, destination):
    tree = Path(tree).resolve()
    if not tree.is_dir():
        raise SystemExit(f'Pristine tree not found: {tree}')
    started = time.perf_counter()
    files = hash_files(tree)
    names = MEMBER_INIS + campaign_member_names()
    members, missing, archives = hash_members(tree, names)
    # The bundled copies are the same bytes; disagreeing would mean one of
    # the two sources is not what it says it is, and that is worth stopping
    # for rather than quietly preferring either.
    for name, digest in bundled_ini_digests().items():
        if name in members and members[name] != digest:
            raise SystemExit(
                f'{name}: configs copy disagrees with the archive member'
            )
        members.setdefault(name, digest)
    manifest = {
        'manifest_version': MANIFEST_VERSION,
        'source_tree': tree.name,
        'archives': archives,
        'files': files,
        'members': members,
    }
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, indent=1, sort_keys=True), encoding='utf-8'
    )
    elapsed = time.perf_counter() - started
    print(f'{destination}')
    print(f'  dosya  : {len(files)}')
    print(f'  uye    : {len(members)} / {len(names)}')
    if missing:
        print(f'  bulunamadi: {len(missing)} -> {missing[:6]}')
    print(f'  arsiv  : {len(archives)}')
    print(f'  boyut  : {destination.stat().st_size / 1024:.0f} KB')
    print(f'  sure   : {elapsed:.1f} sn')
    return manifest


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__.strip().splitlines()[-1].strip())
    destination = (
        Path(argv[2]) if len(argv) > 2
        else ROOT / 'configs' / 'authenticity_manifest.json'
    )
    build(argv[1], destination)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
