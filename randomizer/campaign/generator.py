"""A thing that can generate and record a run without a window.

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

import time

# How many polls a victory marker is given to arrive after the engine
# says the map cleared. The classic window waits the same two, on a clock.
RESTART_GRACE_POLLS = 2


def build(config, missions, state=None):
    """Return something that can generate and record a run."""
    from randomizer.application.archipelago_controller import (
        ArchipelagoController,
    )
    from randomizer.application.enemy_scaling import EnemyScalingController
    from randomizer.application.launch_controller import LaunchController
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
    from randomizer.core.diagnostics import event as log_event

    class Generator(
        SeedController,
        RewardController,
        StateController,
        StartingUnlocksController,
        UnlockDataController,
        ProgressionController,
        LaunchController,
        EnemyScalingController,
        # Composed rather than stubbed: every question the recording path
        # asks it -- what the server sent, which locations a mission has
        # -- it already answers with "there is no session" when the run
        # has no Archipelago on it, which is the only kind of run that
        # reaches here. Stubbing them would have been writing that answer
        # out a second time.
        ArchipelagoController,
    ):
        """The launcher with nothing drawn.

        Everything it inherits either never wanted a window or asks
        whether there is one first. What is overridden below is the
        handful that did: drawing, logging, and the timer a window uses
        to watch a game. Each is answered the way it would be answered
        with no window there -- which is not nothing, because the run
        still has to be written down.
        """

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

            # What a window keeps about the game it started. Nothing is
            # running when one of these is built; a poll fills them in.
            self.active_hook = None
            self.active_game_process = None
            self.active_mission_attempt = None

        def queue_busy_progress(self, *_args, **_kwargs):
            """Say nothing while it works. There is no bar to move."""
            return None

        # --- what a window would have done -------------------------------
        def append_log(self, text, error=False):
            """The launcher's log, where there is no log to write in.

            Kept rather than dropped: these lines are how a player finds
            out what a mission paid out, and the diagnostics file is
            where they are read from when the window is not there.
            """
            log_event(
                'campaign_note', text=str(text), error=bool(error),
            )

        def clear_log(self, *_args, **_kwargs):
            return None

        def redraw_mission_tree(self, *_args, **_kwargs):
            return None

        def refresh_progress_view(self, *_args, **_kwargs):
            return None

        def refresh_grid_tiles(self, *_args, **_kwargs):
            return None

        def update_header_summary(self, *_args, **_kwargs):
            return None

        def process_pending_restart_failure(self):
            """The grace before a restart counts, measured in polls.

            The original measures it on a monotonic clock, which is the
            right thing when one window watches one game from start to
            finish. It is the wrong thing here: the ticket outlives the
            launcher that wrote it, and a monotonic reading from a process
            that has since exited means nothing to the one that reads it
            back. Polls are counted instead -- the same two the comment
            over there is about, and a number that still means two polls
            tomorrow.
            """
            hook = self.active_hook
            if not isinstance(hook, dict):
                return False
            if hook.get('restart_detected_at') is None:
                return False
            code = hook['mission_code']
            if self.is_mission_complete(code):
                hook.pop('restart_detected_at', None)
                hook['polls_since_restart'] = 0
                return False
            waited = int(hook.get('polls_since_restart') or 0) + 1
            hook['polls_since_restart'] = waited
            if waited < RESTART_GRACE_POLLS:
                return False
            hook.pop('restart_detected_at', None)
            hook['polls_since_restart'] = 0
            return self.record_failed_mission_attempt(
                code, 'In-game mission restart detected',
            )

        def schedule_game_close_after_victory(self):
            """Note the win and when it landed. Somebody else closes.

            A window closes the game a couple of seconds after victory,
            and not out of politeness: left alone, Mental Omega walks on
            into the next mission of its own campaign. There is no timer
            here to schedule that on, so the two facts a closer needs --
            that it was won, and when -- are written on the ticket, and
            the poll that reads the ticket does the closing.
            """
            hook = self.active_hook
            if not isinstance(hook, dict) or hook.get('won'):
                return
            hook['won'] = True
            hook['won_at'] = time.time()

        def after(self, _delay, callback=None, *args):
            """There is no event loop to schedule against.

            Nothing here may quietly become a no-op instead: a caller
            that needed a timer needs to be looked at, not silenced.
            """
            raise RuntimeError(
                'The headless launcher has no timer to schedule on'
            )

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
