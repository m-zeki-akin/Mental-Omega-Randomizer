/* The pictures, by the thing they are of.
 *
 * Shared by every screen that lists things the game has art for, because
 * what is kept here is worth keeping across all of them: a unit looked at
 * on the setup screen is the same picture as that unit on the dashboard,
 * and asking twice would be asking twice.
 *
 * They are fetched as rows come into view rather than with the list.
 * There are a few hundred and a screenful is twenty, so what ends up in
 * here is whatever has been looked at -- which is the right amount. A
 * thing with no picture is remembered as having none, or it would be
 * asked about again every time it scrolled past. */

import { call } from './app.js';

/* What the launcher will answer for in one go. Its own ceiling is sixty;
 * asking for more comes back refused, and a refusal would lose the whole
 * batch rather than the tail of it. */
const AT_ONCE = 60;

const held = new Map();

/** The key a picture is kept under, which is what was asked for. */
function nameOf(wanted) {
  return JSON.stringify(wanted);
}

async function fetchSome(asking) {
  const answer = await call('campaign.cameos', {
    units: asking.filter((one) => one.unit).map((one) => one.unit),
    powers: asking.filter((one) => one.power).map((one) => one.power),
  });
  for (const one of asking) {
    const found = one.unit ? answer.units[one.unit] : answer.powers[one.power];
    held.set(nameOf(one), found || '');
  }
}

export const cameos = {
  /** The picture for one thing, or nothing if it has none or is unasked. */
  get: (wanted) => held.get(nameOf(wanted)) || '',

  /** Ask for several, and answer with what every one of them has. */
  load: async (wanted) => {
    const asking = wanted.filter((one) => !held.has(nameOf(one)));
    for (let from = 0; from < asking.length; from += AT_ONCE) {
      try {
        await fetchSome(asking.slice(from, from + AT_ONCE));
      } catch {
        // The pictures are not the point of any screen that shows them.
        // A list that still says what everything is called is a list
        // that works, so what could not be fetched is left unasked --
        // it will be asked for again the next time it is looked at.
        return null;
      }
    }
    return new Map(wanted.map((one) => [nameOf(one), cameos.get(one)]));
  },
};
