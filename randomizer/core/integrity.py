"""Sign the Shop's durable state, and say plainly what that is worth.

The Shop keeps Gems, permanent unlocks and upgrades in three JSON files next
to the executable. Nothing stopped a player opening ``shop_profile.json`` and
changing ``"meta_coins": 88`` to whatever they liked.

**This does not stop a determined cheater and cannot.** The game is offline,
single-player, and the executable is on the player's machine; the key below
comes out of a PyInstaller bundle in minutes. What signing stops is the edit
anyone can make with Notepad in ten seconds, which is the overwhelming
majority of it. Calling that "protection" would be a lie; it is a doorstep.

The reason to have one at all is Archipelago. In a solo run, cheating hurts
only the player doing it, and that is their business. In a multiworld, Gems
buy AP locations, and locations send items to *other people's* games -- there
the cheating has victims who did not consent to it. So the response is shaped
for that: a modified profile still loads and still plays, and only the shared
part is closed off.

Rollback is not addressed and cannot be offline: copy the file, spend, copy it
back. A monotonic counter would only help if it lived somewhere the player
cannot edit, and no such place exists on their own disk.
"""

import hmac
import json
from hashlib import sha256

# Static, and deliberately not derived from the machine. Binding a key to a
# MachineGuid breaks the profile on reinstall or a new disk, and puts a
# machine identifier somewhere it can reach a log file.
_KEY = b'mental-omega-randomizer/shop-state/v1'

SIGNATURE_KEY = '_signature'

# What a document's signature turned out to be.
SIGNED = 'signed'        # present and correct
UNSIGNED = 'unsigned'    # absent: written before signing existed
MODIFIED = 'modified'    # present and wrong, or the document changed under it


def canonical_payload(document):
    """Return the bytes a signature covers: the document without its own."""
    payload = {
        key: value for key, value in dict(document).items()
        if key != SIGNATURE_KEY
    }
    return json.dumps(
        payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        default=str,
    ).encode('utf-8')


def sign(document):
    """Return the document with a signature over its canonical form."""
    signed = {
        key: value for key, value in dict(document).items()
        if key != SIGNATURE_KEY
    }
    signed[SIGNATURE_KEY] = hmac.new(
        _KEY, canonical_payload(signed), sha256
    ).hexdigest()
    return signed


def verify(document):
    """Return SIGNED, UNSIGNED or MODIFIED for one loaded document.

    A document with no signature is not a tampered one. Signing arrives in an
    update, and every profile written before it has none; rejecting those
    would make every existing player a cheater on the day they upgrade.
    """
    document = dict(document)
    claimed = document.get(SIGNATURE_KEY)
    if claimed is None:
        return UNSIGNED
    if not isinstance(claimed, str):
        return MODIFIED
    expected = hmac.new(_KEY, canonical_payload(document), sha256).hexdigest()
    return SIGNED if hmac.compare_digest(claimed, expected) else MODIFIED


def strip_signature(document):
    """Return the document without its signature, for normalisation."""
    return {
        key: value for key, value in dict(document).items()
        if key != SIGNATURE_KEY
    }
