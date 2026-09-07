"""What a Shop run is set up with, as one table both windows can read.

The pacing and the optional trades are a shape of their own -- a number
with a baseline behind it, a card with a drawback on it -- and they are
answered where they always were. What is here is the rest of the setup:
the seed, which factions a shelf is drawn from, which missions a run may
be dealt, and which rewards are kept off the shelf entirely.

Every one of them is a setting the classic window has always had and this
interface had not, and every one lives in the same settings file both
windows read. Nothing here draws anything.
"""

from randomizer.shop.config import (
    FACTION_POOL_SETTING_KEY,
    SHOP_CONFIG,
    SHOP_FACTION_POOLS,
)

from .campaign_settings import (
    GENERATION,
    MAXIMUM_SEED_LENGTH,
    MISSION_POOL_SETTINGS,
)
from .settings_rows import (
    CHOICE,
    SWITCH,
    TEXT,
    TOP,
    by_key,
    full_key,  # noqa: F401  (what the boundary names a row by)
    row as _row,
)
from .settings_rows import rows_for as _rows_for


RUN_SETTINGS = (
    _row(
        'seed', 'Seed name', TEXT,
        'Type one to play a run somebody else played. Blank means a new '
        'one is made when the run starts.',
        where=TOP, maximum_length=MAXIMUM_SEED_LENGTH,
    ),
    _row(
        FACTION_POOL_SETTING_KEY, 'Shelf faction pool', CHOICE,
        'Which side the shop draws units, powers and upgrades from. The '
        'missions stay a mixed campaign whatever this says, and a run '
        'keeps the pool it started with.',
        where=TOP, choices=list(SHOP_FACTION_POOLS),
    ),
)

# The same switches the campaign modes read, from the same table: a Shop
# run is dealt out of the same installed missions.
MISSION_SETTINGS = MISSION_POOL_SETTINGS

# Each hides its rewards from the shelf, from the permanent loadout, and
# from every buff that would have improved them. Chosen before a run and
# fixed for its whole length.
REWARD_SETTINGS = tuple(
    _row(
        group.setting_key, group.display_name, SWITCH,
        f'{group.description} Hides {len(group.target_ids)} of them.',
        where=GENERATION,
    )
    for group in SHOP_CONFIG.reward_exclusion_groups
)

SECTIONS = (
    ('The next run', RUN_SETTINGS),
    ('Missions a run may be dealt', MISSION_SETTINGS),
    ('Rewards kept off the shelf', REWARD_SETTINGS),
)

BY_KEY = by_key(SECTIONS)


def rows_for(mode=''):
    """Return the settings a Shop run shows, section by section."""
    return _rows_for(SECTIONS, mode)
