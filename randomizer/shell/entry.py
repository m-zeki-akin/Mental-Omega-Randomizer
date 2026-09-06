"""Which window a start opens, and what happens when it will not open.

The launcher's entry point asks this before it builds anything. Keeping it
here rather than in the entry script is not tidiness: the packaged build
turns that script into ``__main__``, so a check that wanted to prove the
fallback works could not import it.
"""

import sys
import traceback

from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import LAUNCHER_LOG

from .choice import NEW, chosen


def open_chosen_interface(argv=None, *, warn=True):
    """Open the new interface if that is what was asked for.

    Returns whether it opened. A false answer means the old window, and
    that is also what a failure means: an interface that will not start is
    a reason to fall back to the one that will, not a reason to leave the
    player with nothing.

    ``warn`` is what the self-check turns off. Everything here has to be
    callable without a window appearing, or the row that proves the
    fallback works would open a dialog nobody is there to close.
    """
    import randomizer.shell as package

    try:
        from randomizer.config.player import load_config

        wanted = chosen(sys.argv[1:] if argv is None else argv, load_config())
    except Exception:
        log_event('interface_choice_failed', traceback=traceback.format_exc())
        return False
    if wanted != NEW:
        return False
    try:
        package.run_shell()
        return True
    except Exception:
        detail = traceback.format_exc()
        log_event('interface_failed', traceback=detail)
        if not warn:
            return False
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning(
                'The New Interface Could Not Open',
                '\n\n'.join((
                    'Opening the classic launcher instead.',
                    detail.splitlines()[-1],
                    f'See {LAUNCHER_LOG} for details.',
                )),
            )
            root.destroy()
        except Exception:
            pass
        return False
