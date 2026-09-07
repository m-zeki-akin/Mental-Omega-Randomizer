"""The one door to the run a campaign mode is playing.

Two windows read the same file and one of them writes it, and until now
each reader opened it for itself. That is fine while nothing but the
classic window writes -- and it stops being fine the moment a check has
to be run without touching the run somebody is playing, because there is
no single thing to point somewhere else.

So the file is opened here and nowhere else. A sweep swaps these two
functions for its own, and every reader is redirected at once.
"""

from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import STATE_PATH
from randomizer.core.storage import atomic_write_json, read_json_object


# What a check in a stored run is shaped like. A run written against a
# later shape than this one cannot be read here: the counts against every
# mission would be wrong, and wrong quietly.
CHECK_SCHEMA_VERSION = 18


def standing():
    """Return the run as it is stored, or nothing if there is none.

    A file that cannot be read is the same answer as no file: the caller
    is a screen, and a screen that raises where a run would have been
    leaves the player with nothing at all.
    """
    try:
        if not STATE_PATH.is_file():
            return {}
        loaded = read_json_object(STATE_PATH)
    except (OSError, ValueError):
        log_event('campaign_state_unreadable', path=str(STATE_PATH))
        return {}
    return loaded if isinstance(loaded, dict) else {}


def keep(state):
    """Write the run down, whole, where the other window will find it."""
    atomic_write_json(STATE_PATH, state, indent=None)
