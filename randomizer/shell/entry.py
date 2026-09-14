"""Opening the interface, and what happens when it will not open.

The launcher's entry point calls this rather than building anything
itself. Keeping it here rather than in the entry script is not tidiness:
the packaged build turns that script into ``__main__``, so a check that
wanted to prove a failure is reported could not import it.

There is one interface now. The old window was the fallback for a long
time, and is gone; a failure here is reported and the launcher exits,
because there is nothing else to open.
"""

import sys
import traceback

from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import LAUNCHER_LOG


def warn(title, text):
    """Put one message in front of the player without a toolkit.

    Windows has a dialog of its own, which is the one thing that can be
    relied on when the interface is what failed. Anywhere else the log is
    the message.
    """
    if sys.platform != 'win32':
        return False
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), 0x10)
        return True
    except Exception:
        return False


def open_interface(*, warn_player=True):
    """Open the interface. Returns whether it opened.

    A failure is a false answer rather than an exception, and it is
    logged and shown, because an exe that opens nothing and says nothing
    is the one outcome worse than a broken window.

    ``warn_player`` is what the self-check turns off. Everything here has
    to be callable without a dialog appearing, or the row that proves a
    failure is reported would open one nobody is there to close.
    """
    import randomizer.shell as package

    try:
        package.run_shell()
        return True
    except Exception:
        detail = traceback.format_exc()
        log_event('interface_failed', traceback=detail)
        if warn_player:
            warn(
                'The Launcher Could Not Open',
                '\n\n'.join((
                    detail.splitlines()[-1],
                    f'See {LAUNCHER_LOG} for details.',
                )),
            )
        return False
