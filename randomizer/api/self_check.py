"""Assert the boundary is a boundary.

Three things have to stay true or the interface it was drawn for will grow
through it again: what crosses it survives being written as JSON, a failure
comes back as a reply rather than as an exception nobody catches, and
nothing on this side imports a widget toolkit.
"""

import json
from pathlib import Path

from .contract import ApiError, actions, call, describe_actions


TOOLKIT_NAMES = ('tkinter', 'import tk', 'ttk.', 'webview')


def _package_files():
    """Return the boundary's own modules, minus the one checking them.

    This file names the toolkits it is looking for, so reading itself
    would always find one.
    """
    here = Path(__file__).resolve()
    return sorted(
        path for path in here.parent.glob('*.py') if path != here
    )


def validate_api_contract():
    """Return one row per promise the boundary makes."""
    registered = actions()
    described = describe_actions()

    # Every action answers, and what it answers is plain data. The ones
    # that need a game folder are read here too: an action that only works
    # on a developer's machine is not an action a launcher can offer.
    replies = {}
    for name in registered:
        try:
            replies[name] = call(name)
        except Exception as exc:  # noqa: BLE001 - that is the failure
            replies[name] = {'ok': False, 'error': repr(exc), 'kind': 'raised'}

    json_safe = True
    for reply in replies.values():
        try:
            json.dumps(reply)
        except (TypeError, ValueError):
            json_safe = False

    # Two failures a screen has to be able to survive.
    unknown = call('no.such.action')
    bad_argument = call('skirmish.upgrades')

    toolkit_free = True
    for path in _package_files():
        text = path.read_text(encoding='utf-8', errors='ignore')
        if any(name in text for name in TOOLKIT_NAMES):
            toolkit_free = False

    return {
        'api_actions': len(registered),
        'api_actions_described_valid': bool(
            described
            and len(described) == len(registered)
            and all(entry['summary'] for entry in described)
        ),
        'api_replies_json_safe_valid': bool(json_safe and replies),
        'api_failures_are_replies_valid': bool(
            unknown.get('ok') is False
            and unknown.get('kind') == 'UnknownAction'
            and bad_argument.get('ok') is False
            and bad_argument.get('kind') == 'ApiError'
            and bad_argument.get('error')
        ),
        # Every action that does not need a run of its own answers cleanly.
        'api_actions_answer_valid': bool(
            replies
            and all(
                reply.get('ok')
                for name, reply in replies.items()
                if name != 'skirmish.upgrades'
            )
        ),
        # The point of the boundary: the launcher's rules never learn what
        # is drawing them, and this side never learns either.
        'api_toolkit_free_valid': toolkit_free,
        'api_contract_valid': bool(
            json_safe
            and toolkit_free
            and unknown.get('ok') is False
            and described
        ),
    }
