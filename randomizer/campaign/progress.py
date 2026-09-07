"""How far a campaign run got, read from the run itself.

Every question here is answered from the stored run and nothing else --
no window, no controller, no installed rules. That is what lets both
interfaces ask, and it is why the answers are the same in both.

The one question that is not answered here is Grid Mode's. A grid decides
what is open from a layout it also keeps up to date, which is a change to
the run rather than a reading of it; the classic window owns that, and
this module answers the ordered modes only.
"""

from randomizer.missions.catalogue import STARTING_UNLOCKED_MISSIONS
from randomizer.rewards.display import check_rewards


def order(state):
    """Return the missions of this run, in the order it plays them."""
    listed = (state or {}).get('mission_order')
    return [str(code) for code in listed] if isinstance(listed, list) else []


def checks(state, code):
    """Return what one mission is checked for, or nothing."""
    held = (state or {}).get('mission_checks')
    listed = held.get(code) if isinstance(held, dict) else None
    return listed if isinstance(listed, list) else []


def check_counts(state, code):
    """Return how many of one mission's rewards are in hand, and of how many.

    A run that only pays out on victory counts what victory pays; one
    that pays per objective counts every objective, and an objective
    with no reward still counts as something to do.
    """
    listed = checks(state, code)
    if not listed:
        return (0, 0)
    done = sum(
        len(check_rewards(check))
        for check in listed
        if check.get('unlocked') or check.get('released')
    )
    if (state or {}).get('rewards_on_victory_only', False):
        return (done, sum(len(check_rewards(check)) for check in listed))
    return (done, sum(max(1, len(check_rewards(check))) for check in listed))


def is_complete(state, code):
    """Return whether one mission has been won."""
    listed = checks(state, code)
    if listed:
        return any(
            check.get('id') == 'victory' and check.get('unlocked')
            for check in listed
        )
    return code in (state or {}).get('completed_missions', [])


def is_started(state, code):
    """Return whether one mission has been played but not yet won."""
    if not state or is_complete(state, code):
        return False
    return (
        code in state.get('started_missions', [])
        or any(check.get('unlocked') for check in checks(state, code))
    )


def unlocked_codes(state):
    """Return the missions open to be played, in the run's own order.

    One more opens for each one won, on top of the few a run begins with.
    Grid Mode does not come through here: what is open there is a shape
    on a board rather than a count along a list.
    """
    listed = order(state)
    if not listed:
        return []
    begun_with = (state or {}).get(
        'starting_unlocked_missions', STARTING_UNLOCKED_MISSIONS
    )
    try:
        begun_with = int(begun_with)
    except (TypeError, ValueError):
        begun_with = STARTING_UNLOCKED_MISSIONS
    won = len((state or {}).get('completed_missions', []) or ())
    return listed[:min(len(listed), max(0, begun_with) + won)]


def next_code(state):
    """Return the first mission that is open and not yet won, or nothing."""
    for code in unlocked_codes(state):
        if not is_complete(state, code):
            return code
    return None


def grid_states(state):
    """Return what the board says about each mission, if there is a board.

    Read rather than worked out. Grid keeps its own tiles up to date as a
    run is played, and bringing them up to date is a change to the run --
    which a screen that only looks at one has no business making.
    """
    grid = (state or {}).get('grid')
    nodes = grid.get('nodes') if isinstance(grid, dict) else None
    if not isinstance(nodes, dict):
        return {}
    return {
        str(code): str((node or {}).get('state') or '')
        for code, node in nodes.items()
        if isinstance(node, dict)
    }
