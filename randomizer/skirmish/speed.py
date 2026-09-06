"""Making the in-game speed slider do nothing.

A run is played at one speed. Which one is a setting, and it is written
into both the spawn file and the game's own options -- but the slider in
the in-game menu is still there and still moves, and a run whose pacing
can be changed mid-battle is not the run its rewards were tuned against.

The slider itself lives in the game executable and is not ours to remove.
What is ours is what each of its positions means. Phobos lets a mod
redefine the speed table -- ``[GlobalControls] CustomGS`` with a delay per
step -- so every position is given the same delay as the speed the run is
locked to. The slider still slides; the game plays at one speed whatever it
says.

Written as map code, like everything else a battle needs, so it lasts
exactly as long as the battle does and no file in the game folder is left
holding a rule the player did not ask for.
"""

from randomizer.core.diagnostics import event as log_event

from .mapfile import merge_into_map


# The engine's speed steps, fastest first. Its own numbering: the value in
# spawn.ini and in the options file is this index, which is why the client
# calls index 1 "5 Faster".
SPEED_STEPS = 7
# Phobos reads these from the rules, and a map is rules.
GLOBAL_CONTROLS = 'GlobalControls'
CUSTOM_SPEEDS = 'CustomGS'


def locked_speed_code(value, *, steps=SPEED_STEPS):
    """Return the map code that makes every speed step play at ``value``.

    ``DefaultDelay`` is the frames a step waits between updates, and the
    engine's own table is the step's own index -- 0 waits for nothing and
    is the fastest. Giving every step the locked speed's delay leaves the
    slider free to move and the game unaffected by it.
    """
    try:
        delay = max(0, int(value))
    except (TypeError, ValueError):
        return {}
    controls = {CUSTOM_SPEEDS: 'yes'}
    for step in range(max(1, int(steps))):
        controls[f'{CUSTOM_SPEEDS}{step}.DefaultDelay'] = str(delay)
    return {GLOBAL_CONTROLS: controls}


def apply_locked_speed(map_path, value, *, steps=SPEED_STEPS):
    """Write the locked speed table into the map, and say what it cost."""
    code = locked_speed_code(value, steps=steps)
    if not code:
        return 0
    keys = merge_into_map(map_path, code)
    log_event('skirmish_speed_locked', speed=value, steps=steps, keys=keys)
    return keys
