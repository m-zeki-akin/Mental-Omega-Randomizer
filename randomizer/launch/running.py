"""Whether Mental Omega is up, when nobody is holding onto it.

A launcher that started the game holds its process and can simply ask. A
launcher that has just started, and finds a battle the last one wrote down
and never recorded, holds nothing -- and the difference between a battle
still being played and a battle abandoned is the difference between
waiting and charging a life for it.

So this asks the machine rather than a handle. It is the only thing here
that does, and it is deliberately dumb: a name, a process list, a boolean.
"""

import subprocess
import sys

from randomizer.core.paths import GAME_EXE


def game_is_running(name=None):
    """Whether a copy of the game is running, by name.

    An unanswerable question -- no process list, a command that failed --
    is answered ``False``: the alternative is a launcher that waits
    forever for a game nobody can see.
    """
    wanted = (name or GAME_EXE.name).lower()
    try:
        if sys.platform == 'win32':
            found = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq {wanted}', '/NH'],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                timeout=10,
            ).stdout
        else:
            found = subprocess.run(
                ['pgrep', '-f', wanted],
                capture_output=True, text=True, timeout=10,
            ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return wanted in found.lower()
