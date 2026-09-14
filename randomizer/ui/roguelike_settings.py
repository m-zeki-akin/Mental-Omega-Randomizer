"""What the two roguelikes share, as one table both draw.

Shop Mode and the Skirmish Shop are the same kind of game -- a run with
lives, a shop between fights, and a board when it ends -- and a setting
that says which rewards may reach a shelf at all is a setting about that
kind, not about one of them. So it is one table, stored in the one
block both modes read, and each mode's Setup screen draws it beside its
own.

Nothing here draws anything.
"""

from randomizer.shop.config import SHOP_CONFIG

from .campaign_settings import GENERATION
from .settings_rows import SWITCH, by_key, row as _row
from .settings_rows import rows_for as _rows_for


# Each hides its rewards from every shelf a roguelike deals: the campaign
# shop's, the permanent loadout, the skirmish's, and every buff that
# would have improved them. Chosen before a run and fixed for its whole
# length.
REWARD_SETTINGS = tuple(
    _row(
        group.setting_key, group.display_name, SWITCH,
        f'{group.description} Hides {len(group.target_ids)} of them.',
        where=GENERATION,
    )
    for group in SHOP_CONFIG.reward_exclusion_groups
)

SECTIONS = (
    ('Rewards kept off the shelf', REWARD_SETTINGS),
)

BY_KEY = by_key(SECTIONS)


def rows_for(mode=''):
    """Return the settings both roguelikes show, section by section."""
    return _rows_for(SECTIONS, mode)


def kept_off_shelf(config):
    """Return the reward targets the player has switched off, upper-cased.

    Read from the same settings block either roguelike writes, so a switch
    turned on for one is on for the other. Empty when nothing is off,
    which is what a shelf that hides nothing is drawn from.
    """
    generation = (config or {}).get(GENERATION) or {}
    kept = set()
    for group in SHOP_CONFIG.reward_exclusion_groups:
        if generation.get(group.setting_key):
            kept.update(str(one).upper() for one in group.target_ids)
    return frozenset(kept)
