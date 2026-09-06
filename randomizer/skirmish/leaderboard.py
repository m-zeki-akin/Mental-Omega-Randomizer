"""Where a finished run goes.

A run that ends is deleted or left sitting as a dead entry in the run list,
and either way what it did is gone. This keeps the one thing worth keeping:
how far it got, and what it did on the way.

Signed and written atomically, like the run store beside it -- not because
a leaderboard is worth protecting, but because a file the launcher reads
back and shows as fact should be a file the launcher wrote.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from randomizer.core.integrity import sign
from randomizer.core.paths import APP_DIR
from randomizer.core.storage import atomic_write_opaque, read_opaque_object

from .stats import RunStats, normalize_stats


LEADERBOARD_PATH = APP_DIR / 'skirmish_leaderboard.dat'
LEADERBOARD_SCHEMA_VERSION = 1
# How many runs the board keeps. Long enough to hold a season of them and
# short enough that the file stays something a person could read.
MAX_ENTRIES = 100


@dataclass(frozen=True)
class BoardEntry:
    """One finished run, as the board remembers it."""

    run_id: str
    seed: str
    army: str
    ally: str
    started: str
    ended: str
    outcome: str
    battle: int
    tier: int
    nightmare: int
    stats: RunStats

    @property
    def reached(self):
        """How far it got, as one sortable number."""
        return (self.nightmare, self.tier, self.battle)

    def to_dict(self) -> dict[str, Any]:
        return {
            'run_id': self.run_id,
            'seed': self.seed,
            'army': self.army,
            'ally': self.ally,
            'started': self.started,
            'ended': self.ended,
            'outcome': self.outcome,
            'battle': self.battle,
            'tier': self.tier,
            'nightmare': self.nightmare,
            'stats': self.stats.to_dict(),
        }


def _entry(document):
    if not isinstance(document, dict):
        return None
    try:
        return BoardEntry(
            run_id=str(document.get('run_id') or ''),
            seed=str(document.get('seed') or ''),
            army=str(document.get('army') or ''),
            ally=str(document.get('ally') or ''),
            started=str(document.get('started') or ''),
            ended=str(document.get('ended') or ''),
            outcome=str(document.get('outcome') or ''),
            battle=max(0, int(document.get('battle') or 0)),
            tier=max(0, int(document.get('tier') or 0)),
            nightmare=max(0, int(document.get('nightmare') or 0)),
            stats=normalize_stats(document.get('stats')),
        )
    except (TypeError, ValueError):
        return None


def load_board(path=None):
    """Return every finished run the board holds, furthest first.

    A board that has never been written is an empty one, not an error: the
    first run to end is what creates the file.
    """
    path = Path(path or LEADERBOARD_PATH)
    if not path.is_file():
        return ()
    try:
        document = read_opaque_object(path)
    except (OSError, ValueError):
        # Unreadable is the same as empty here. A board is a record of
        # runs, not something a run depends on.
        return ()
    entries = []
    if isinstance(document, dict):
        for row in document.get('entries') or ():
            entry = _entry(row)
            if entry is not None:
                entries.append(entry)
    return tuple(sorted(
        entries,
        key=lambda item: (item.reached, item.stats.score),
        reverse=True,
    ))


def save_board(entries, path=None):
    """Write the board, keeping the furthest runs when it is full."""
    kept = tuple(sorted(
        entries,
        key=lambda item: (item.reached, item.stats.score),
        reverse=True,
    ))[:MAX_ENTRIES]
    document = {
        'schema_version': LEADERBOARD_SCHEMA_VERSION,
        'entries': [entry.to_dict() for entry in kept],
    }
    atomic_write_opaque(path or LEADERBOARD_PATH, sign(document))
    return kept


def record_run(entry, path=None):
    """Add one finished run to the board, replacing an earlier write of it."""
    existing = [
        item for item in load_board(path) if item.run_id != entry.run_id
    ]
    return save_board(existing + [entry], path)


def record_finished_run(run, outcome, *, ended='', path=None):
    """Put a run that has ended on the board, whatever ended it.

    Two things end a run -- giving up and running out of lives -- and
    there is now more than one screen that can be looking when either
    happens. Describing the run is the same work every time, so it is
    done once here rather than wherever the news arrived.
    """
    from datetime import date

    from .factions import country_by_index

    player = country_by_index(run.player_country)
    ally = country_by_index(run.ally_country)
    return record_run(
        BoardEntry(
            run_id=run.run_id,
            seed=run.seed,
            army=player.display if player else str(run.player_country),
            ally=ally.display if ally else str(run.ally_country),
            started=run.created,
            ended=ended or date.today().isoformat(),
            outcome=outcome,
            battle=run.battle,
            tier=run.tier,
            nightmare=run.nightmare,
            stats=run.stats,
        ),
        path,
    )


BOARD_COLUMNS = (
    ('reached', 'Reached', 150),
    ('army', 'Army', 150),
    ('outcome', 'Outcome', 90),
    ('battles', 'Battles', 80),
    ('kills', 'Kills', 80),
    ('score', 'Score', 100),
    ('ore', 'Ore earned', 100),
    ('ended', 'Ended', 100),
)


def reached_text(entry):
    """How far one run got, in words."""
    round_name = f'Nightmare {entry.nightmare}, ' if entry.nightmare else ''
    if entry.tier <= 0:
        return f'{round_name}warmup'
    return f'{round_name}tier {entry.tier}, battle {entry.battle}'


def board_row(entry):
    """Return one board row, in the order ``BOARD_COLUMNS`` names."""
    stats = entry.stats
    return (
        reached_text(entry),
        f'{entry.army} + {entry.ally}' if entry.ally else entry.army,
        entry.outcome,
        f'{stats.won} / {stats.battles}',
        f'{stats.kills:,}',
        f'{stats.score:,}',
        f'{stats.ore_earned:,}',
        entry.ended,
    )
