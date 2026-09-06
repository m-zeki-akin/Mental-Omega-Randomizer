"""Opening the window, and answering what is drawn in it.

pywebview hosts the pages in the system's own WebView2, which Windows 10
and 11 ship. The page gets exactly one thing to call -- ``call`` -- and
everything it asks for goes through ``randomizer.api``, which is where the
launcher decides what an interface may know.
"""

from pathlib import Path
import sys

from randomizer.api.contract import call as api_call, describe_actions
from randomizer.core.diagnostics import event as log_event


class ShellError(RuntimeError):
    """The window could not be opened, with a reason worth showing."""


WINDOW_TITLE = 'Mental Omega Randomizer'
# Big enough for three battle cards beside each other and a shelf of six
# below them, which is what the Skirmish screen is.
WINDOW_SIZE = (1180, 780)
MINIMUM_SIZE = (900, 620)
BACKGROUND = '#0d0f13'


def web_root():
    """Return the folder the interface is served from.

    Frozen, the pages sit beside the bundle's other data; from a checkout,
    they sit next to the package.
    """
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) / 'web'
    return Path(__file__).resolve().parents[2] / 'web'


class Bridge:
    """What the page may call. One method, on purpose.

    Every screen asks for things by name, so what an interface may do is a
    list in ``randomizer.api`` rather than a set of methods that grows here
    until this file is the interface.
    """

    def call(self, name, args=None):
        return api_call(str(name), **(args or {}))

    def actions(self):
        return {'ok': True, 'result': list(describe_actions())}


def run_shell(*, debug=False, page='index.html'):
    """Open the launcher's window and return when it closes."""
    try:
        import webview
    except ImportError as exc:  # pragma: no cover - a build problem
        raise ShellError(
            'The interface needs pywebview, which is not in this build'
        ) from exc

    root = web_root()
    entry = root / page
    if not entry.is_file():
        raise ShellError(f'The interface is missing its pages: {entry}')

    log_event('shell_starting', page=str(entry), debug=bool(debug))
    window = webview.create_window(
        WINDOW_TITLE,
        str(entry),
        js_api=Bridge(),
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=MINIMUM_SIZE,
        background_color=BACKGROUND,
    )
    webview.start(debug=bool(debug))
    log_event('shell_closed')
    return window
