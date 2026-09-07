"""A thing that can generate a run without a window in front of it.

Generating a campaign run is not one function: it is a dozen that read
each other -- which rewards the pool may hold, what a mission is checked
for, which units a seed opens with -- and they were written as methods on
the classic window's controllers. They are not about a window, and most
of them say so: the ones that read a control read it only after asking
whether there is one, which is a seam somebody left open on purpose.

This walks through it. The controllers are composed into one object that
has the three things they actually need -- the settings, the run, the
installed missions -- and none of the widgets. It is a real object, not a
stand-in: the code that runs is the code the classic window runs, which
is the only way the two interfaces can generate the same run from the
same settings.

What is honest to say about it: the classic window's modules are still
where that code lives, so building one of these imports them. Moving them
here is worth doing and is a job of its own; until then this is the seam,
and it is a narrow one.
"""


def build(config, missions, state=None):
    """Return something that can generate a run from these settings."""
    from randomizer.application.progression_controller import (
        ProgressionController,
    )
    from randomizer.application.reward_controller import RewardController
    from randomizer.application.seed_controller import SeedController
    from randomizer.application.starting_unlocks import (
        StartingUnlocksController,
    )
    from randomizer.application.state_controller import StateController
    from randomizer.application.unlock_data import UnlockDataController

    class Generator(
        SeedController,
        RewardController,
        StateController,
        StartingUnlocksController,
        UnlockDataController,
        ProgressionController,
    ):
        """The generation half of the launcher, with nothing drawn."""

        def __init__(self, config, missions, state):
            self.config = config
            self.state = state or {}
            self.missions = list(missions)
            self._mission_by_code = {
                mission['code']: mission for mission in self.missions
            }
            block = config.get('generation') or {}
            for name, key in (
                ('excluded_mission_codes', 'excluded_mission_codes'),
                ('excluded_unit_access_ids', 'excluded_unit_access_ids'),
                ('excluded_superweapon_ids', 'excluded_superweapon_ids'),
            ):
                setattr(self, name, {
                    str(value).upper() for value in block.get(key, [])
                    if str(value).strip()
                })

        def queue_busy_progress(self, *_args, **_kwargs):
            """Say nothing while it works. There is no bar to move."""
            return None

    return Generator(config, missions, state)


def installed_missions():
    """Return the campaign as this install has it, or nothing."""
    from randomizer.core.paths import BATTLE_CLIENT_INI
    from randomizer.missions.catalogue import (
        FALLBACK_OBJECTIVE_COUNT,
        parse_missions,
    )

    try:
        return parse_missions(BATTLE_CLIENT_INI, FALLBACK_OBJECTIVE_COUNT)
    except (OSError, ValueError):
        return []
