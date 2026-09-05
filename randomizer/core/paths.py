"""Shared filesystem paths for the Mental Omega randomizer launcher."""
import shutil
import sys
from hashlib import sha256
from pathlib import Path

import os

FROZEN = bool(getattr(sys, 'frozen', False))
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The folder player data used to live in, beside the executable.
LEGACY_APP_DIRECTORY = 'RandomizerLauncherData'
PLAYER_DATA_DIRECTORY = 'MentalOmegaRandomizer'


def _development_game_root(default):
    override = os.environ.get('MO_RANDOMIZER_GAME_ROOT', '').strip()
    return Path(override).resolve() if override else default


def _local_app_data():
    configured = os.environ.get('LOCALAPPDATA', '').strip()
    if configured:
        return Path(configured)
    return Path.home() / 'AppData' / 'Local'


def _install_key(game_root):
    """Return the short per-installation folder name.

    Data used to sit inside the game folder, so two installations never
    shared it. Keeping that true matters more than a readable path: the
    launcher's own README recommends a separate clean installation, and
    merging a modded install's profile into a clean one is not something a
    player would ask for. The folder names the installation it belongs to in
    install.txt, since the hash on its own tells nobody anything.
    """
    resolved = str(Path(game_root).resolve()).lower()
    return sha256(resolved.encode('utf-8')).hexdigest()[:8]


def _migrate_player_data(source, destination):
    """Move an existing RandomizerLauncherData across, or keep using it.

    Copied to a staging folder and renamed into place, rather than moved: the
    game folder and %LOCALAPPDATA% are usually on different drives, so a move
    is a copy that can fail halfway and leave a half-profile behind under the
    name everything afterwards trusts. On any failure the old folder stays
    authoritative and the launcher keeps working from it -- a launcher that
    cannot move player data must never be a launcher that loses it.
    """
    if destination.exists() or not source.is_dir():
        return destination
    staging = destination.with_name(destination.name + '.migrating')
    try:
        shutil.rmtree(staging, ignore_errors=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, staging)
        os.replace(staging, destination)
    except OSError:
        shutil.rmtree(staging, ignore_errors=True)
        return source
    shutil.rmtree(source, ignore_errors=True)
    return destination


def _player_data_dir(game_root):
    override = os.environ.get('MO_RANDOMIZER_DATA_DIR', '').strip()
    if override:
        return Path(override).resolve()
    destination = (
        _local_app_data() / PLAYER_DATA_DIRECTORY / _install_key(game_root)
    )
    legacy = game_root / LEGACY_APP_DIRECTORY
    try:
        resolved = _migrate_player_data(legacy, destination)
    except Exception:
        # Housekeeping must never be the reason the launcher will not open.
        return legacy if legacy.is_dir() else destination
    try:
        resolved.mkdir(parents=True, exist_ok=True)
        (resolved / 'install.txt').write_text(
            str(game_root) + chr(10), encoding='utf-8'
        )
    except OSError:
        pass
    return resolved

SOURCE_DIR = PROJECT_ROOT
WINDOW_ICON_PATH = SOURCE_DIR / 'mo-logo-puzzle-icon.ico'

# A one-file build is placed directly in the Mental Omega folder. PyInstaller
# expands bundled modules to a temporary directory, so __file__ cannot locate
# the game or persistent state in frozen builds.
if FROZEN:
    GAME_ROOT = Path(sys.executable).resolve().parent
    # Not beside the executable any more. That folder is under Program Files
    # on a Steam installation, where writing depends on either running
    # elevated or on Windows silently redirecting to VirtualStore, and where
    # Steam's own file verification can remove it. %LOCALAPPDATA% is writable
    # without either, and survives a game update.
    APP_DIR = _player_data_dir(GAME_ROOT)
else:
    APP_DIR = SOURCE_DIR
    # Development runs sit beside the repository, not inside an installation,
    # so anything read from the installed game -- rules, art, archives -- is
    # absent and silently falls back to committed data. Pointing this at a
    # real install is the only way a check that reads installed rules can
    # fail in development instead of passing on stock values.
    GAME_ROOT = _development_game_root(SOURCE_DIR.parent)
GAME_LAUNCHER_EXE = GAME_ROOT / 'Syringe.exe'
GAME_EXE = GAME_ROOT / 'gamemd.exe'
SPAWN_INI = GAME_ROOT / 'spawn.ini'
OPTIONS_INI = GAME_ROOT / 'RA2MO.ini'
YR_OPTIONS_INI = GAME_ROOT / 'RA2MD.INI'
UIMD_INI = GAME_ROOT / 'uimd.ini'
DEBUG_LOG = GAME_ROOT / 'debug' / 'debug.log'
RULESMO_INI = GAME_ROOT / 'rulesmo.ini'
DISABLED_RULESMO_INI = GAME_ROOT / 'rulesmo.ini.randomizer-disabled'
BATTLE_CLIENT_INI = GAME_ROOT / 'INI' / 'BattleClient.ini'
STATE_PATH = APP_DIR / 'randomizer_state.json'
# Shop state is stored as an opaque blob rather than readable JSON, so the
# .json names it used to carry would now be a lie. The old names are still
# read once, then renamed; see randomizer.shop.persistence.
SHOP_PROFILE_PATH = APP_DIR / 'shop_profile.dat'
SHOP_RUN_PATH = APP_DIR / 'shop_run.dat'
SHOP_TRANSACTION_PATH = APP_DIR / 'shop_transaction.dat'
# Skirmish runs share no profile and no meta progression -- one session
# does not touch another -- so the mode keeps a single file holding its
# list of runs, and there is no second document to stay consistent with.
SKIRMISH_RUNS_PATH = APP_DIR / 'skirmish_runs.dat'
BACKUP_DIR = APP_DIR / 'backups'
EXTRACTED_MAP_DIR = APP_DIR / 'extracted_maps'
GENERATED_MAP_DIR = APP_DIR / 'generated_maps'
CAMEO_CACHE_DIR = APP_DIR / 'cameo_cache'
CONFIG_DIR = APP_DIR / 'configs' / 'player'
LEGACY_CONFIG_DIR = APP_DIR / 'config'
LOG_DIR = APP_DIR / 'logs'
LAUNCHER_LOG = LOG_DIR / 'launcher.log'
MAP_RENDERER_DIR = GAME_ROOT / 'Map Renderer'


def validate_player_data_contract():
    """Prove the player-data folder moves without ever losing a profile.

    Migration runs once, on the first launch after an upgrade, against the
    only copy of a player's Gems and unlocks that exists. There is no second
    chance and no undo, so the failure path -- keep the old folder, keep
    playing -- is checked as carefully as the success path.
    """
    import tempfile

    checks = {}
    with tempfile.TemporaryDirectory(prefix='mo-player-data-') as temporary:
        root = Path(temporary)
        local = root / 'local'
        previous = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = str(local)
        try:
            game = root / 'game'
            legacy = game / LEGACY_APP_DIRECTORY
            legacy.mkdir(parents=True)
            (legacy / 'shop_profile.dat').write_bytes(b'profile')

            moved = _player_data_dir(game)
            checks['migrates_existing_data'] = (
                (moved / 'shop_profile.dat').read_bytes() == b'profile'
                and not legacy.exists()
            )
            checks['records_its_installation'] = (
                (moved / 'install.txt').read_text(encoding='utf-8').strip()
                == str(game)
            )
            checks['outside_game_folder'] = game not in moved.parents
            checks['migration_is_idempotent'] = _player_data_dir(game) == moved

            other = root / 'other-install'
            other.mkdir()
            checks['installations_stay_separate'] = (
                _player_data_dir(other) != moved
            )

            # The move is a cross-drive copy in practice. One that dies
            # halfway must leave the launcher reading the folder it started
            # from, with everything still in it.
            failing = root / 'failing'
            failing_legacy = failing / LEGACY_APP_DIRECTORY
            failing_legacy.mkdir(parents=True)
            (failing_legacy / 'shop_profile.dat').write_bytes(b'kept')
            real_copytree = shutil.copytree

            def refuse(*arguments, **keywords):
                raise OSError('simulated copy failure')

            shutil.copytree = refuse
            try:
                fallback = _player_data_dir(failing)
            finally:
                shutil.copytree = real_copytree
            checks['migration_failure_keeps_legacy'] = (
                fallback == failing_legacy
                and (fallback / 'shop_profile.dat').read_bytes() == b'kept'
            )
        finally:
            if previous is None:
                os.environ.pop('LOCALAPPDATA', None)
            else:
                os.environ['LOCALAPPDATA'] = previous

    from randomizer.core.runtime_cleanup import (
        LEGACY_RUNTIME_DIRECTORY,
        _search_roots,
    )

    checks['legacy_runtime_directory_swept'] = LEGACY_RUNTIME_DIRECTORY in {
        root.name for root in _search_roots(Path(__file__).parent)
    }
    # The extraction folder belongs in the system temporary directory. A
    # packaged build that puts it back in the game folder fails here.
    bundle = getattr(sys, '_MEIPASS', None)
    checks['runtime_outside_game_folder'] = (
        bundle is None or GAME_ROOT not in Path(bundle).resolve().parents
    )
    return checks
