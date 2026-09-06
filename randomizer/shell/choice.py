"""Which interface the launcher opens, and how that is decided.

There are two now. The old window is still the whole launcher; the new one
draws a mode and a half. Neither is ready to be the only one, so the player
chooses, and the choice is remembered -- a launcher that has to be started
from a terminal to look the way somebody wants is a launcher they will not
look at twice.

A flag beats the remembered choice, so one run can be different without
changing what a double-click does.
"""

from randomizer.core.diagnostics import event as log_event


CLASSIC = 'classic'
NEW = 'new'
INTERFACES = (CLASSIC, NEW)
# What a command line may say. --shell is what the interface was built
# under and is kept; --interface reads better and means the same.
FLAGS = {
    '--classic': CLASSIC,
    '--shell': NEW,
    '--interface': NEW,
    '--new-interface': NEW,
}
CONFIG_KEY = 'interface'


def flagged(argv):
    """Return the interface a command line asks for, or nothing."""
    for argument in argv or ():
        wanted = FLAGS.get(str(argument).strip().lower())
        if wanted:
            return wanted
    return None


def remembered(config):
    """Return the interface the player last settled on."""
    wanted = str((config or {}).get(CONFIG_KEY) or '').strip().lower()
    return wanted if wanted in INTERFACES else CLASSIC


def chosen(argv=None, config=None):
    """Return the interface to open: what was asked for, or what was kept."""
    return flagged(argv) or remembered(config)


def remember(name):
    """Keep one interface as what a double-click opens."""
    from randomizer.config.player import load_config, save_config

    wanted = name if name in INTERFACES else CLASSIC
    config = load_config()
    if remembered(config) == wanted:
        return wanted
    config[CONFIG_KEY] = wanted
    save_config(config)
    log_event('interface_chosen', interface=wanted)
    return wanted
