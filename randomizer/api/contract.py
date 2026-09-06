"""What a screen may ask, and how the answer comes back.

An action is a named call with plain-data arguments and a plain-data
result. Naming them in one registry buys three things: a screen can ask
what exists rather than being written against a list somebody remembered,
a failure comes back as a message rather than as a traceback in a console
nobody is reading, and every call can be logged in one place.

The shape of a reply never varies::

    {'ok': True,  'result': <plain data>}
    {'ok': False, 'error': 'what went wrong', 'kind': 'ApiError'}

A screen that has to branch on how a call failed reads ``kind``; one that
only has to tell the player reads ``error``.
"""

from dataclasses import dataclass
from typing import Any, Callable

from randomizer.core.diagnostics import event as log_event


class ApiError(RuntimeError):
    """A call that failed for a reason worth telling the player."""


# What an action is for. A reading answers whenever it is asked; a command
# changes something and is allowed to refuse -- there may be no run to buy
# for. Both matter to a screen, and they matter differently.
READ = 'read'
COMMAND = 'command'


@dataclass(frozen=True)
class Action:
    """One thing a screen may ask the launcher to do."""

    name: str
    call: Callable[..., Any]
    summary: str
    kind: str = READ

    def __call__(self, **arguments):
        return self.call(**arguments)


_ACTIONS: dict[str, Action] = {}


def action(name, summary='', kind=READ):
    """Register one call under a name a screen can ask for."""

    def register(function):
        if name in _ACTIONS:
            raise RuntimeError(f'Two API actions are named {name!r}')
        _ACTIONS[name] = Action(
            name=name,
            call=function,
            summary=summary or (function.__doc__ or '').strip().split('\n')[0],
            kind=kind,
        )
        return function

    return register


def actions():
    """Return every registered action, by name."""
    _load_actions()
    return dict(_ACTIONS)


def describe_actions():
    """Return what a screen may ask, for a screen that wants to know."""
    return tuple(
        {'name': entry.name, 'summary': entry.summary, 'kind': entry.kind}
        for entry in sorted(actions().values(), key=lambda item: item.name)
    )


def call(name, **arguments):
    """Run one action and return the reply a screen reads.

    A failure is a reply, not an exception: the caller is on the other side
    of a bridge that cannot carry one, and a screen that gets nothing back
    has no way to say what happened.
    """
    entry = actions().get(str(name))
    if entry is None:
        return {
            'ok': False,
            'error': f'The launcher has no action named {name!r}',
            'kind': 'UnknownAction',
        }
    try:
        return {'ok': True, 'result': entry(**(arguments or {}))}
    except ApiError as exc:
        return {'ok': False, 'error': str(exc), 'kind': 'ApiError'}
    except Exception as exc:  # noqa: BLE001 - the bridge cannot carry one
        log_event(
            'api_action_failed',
            action=str(name),
            error_type=exc.__class__.__name__,
            error=str(exc),
        )
        return {
            'ok': False,
            'error': f'{exc.__class__.__name__}: {exc}',
            'kind': exc.__class__.__name__,
        }


def _load_actions():
    """Import the modules that register actions, once."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from . import skirmish  # noqa: F401  (importing is what registers)


_LOADED = False
