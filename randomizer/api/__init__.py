"""The boundary between what the launcher knows and what a screen shows.

Everything under ``randomizer`` outside this package answers in objects:
runs, offers, upgrades, maps. Everything a user interface deals in is text,
numbers and lists it can lay out. This is the one place the two meet, and
it is deliberately thin -- an interface that reaches past it into the
domain is an interface that has to be rewritten with the next one.

Two rules hold it in shape:

* Nothing here imports a widget toolkit, and nothing in the domain imports
  this. The launcher's rules never learn what is drawing them.
* Every call takes and returns plain data -- dicts, lists, strings,
  numbers, booleans. What crosses this line has to survive being written
  as JSON, because that is exactly what happens to it.
"""

from .contract import ApiError, action, actions, describe_actions


__all__ = ['ApiError', 'action', 'actions', 'describe_actions']
