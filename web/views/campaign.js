/* The campaign's setup: how the next run will be generated.
 *
 * One screen for Classic, Mission List and Grid, because they are the
 * same campaign in a different order and share all but three of their
 * settings. Which rows those three are is the launcher's to say, not this
 * screen's: it draws the sections it is given, in the order it is given
 * them, and a row it has never heard of would still be drawn.
 *
 * Generating is here too now, at the end where it belongs: everything
 * above it is what the run will be made of, and the press is what makes
 * it. Playing the run is still the classic window's. */

import { act, call, refresh, register } from '../app.js';
import { button, el, notice, panel, section } from '../components/index.js';
import { searchesIn, settingsSections } from '../components/settings.js';

/* The long lists, once each. What a setting may name comes from the
 * installed rules: a few hundred entries, the same on every reading, and
 * the same for every screen that asks. Asking again after each change
 * would send all of it back for nothing. */
const catalogues = new Map();

/* What has been typed into each search box, kept across a redraw. A
 * change is saved, saving redraws the screen, and a player adding three
 * units to a list should not have to type the same word three times. */
const queries = new Map();

async function fetchCatalogue(name) {
  if (!catalogues.has(name)) {
    const answer = await call('campaign.catalogue', { name });
    catalogues.set(name, answer.entries || []);
  }
  return catalogues.get(name);
}

/* Which search boxes had their list down. Kept for the same reason the
 * typing is: picking one entry saves a setting, saving draws the screen
 * again, and a list that shut every time somebody used it would make
 * excluding five things a matter of fifteen presses. */
const opens = new Map();

/* Things named on a screen that the launcher has nothing to keep for
 * yet: a unit picked out to bar an upgrade from, before any upgrade has
 * been barred. Kept here so that naming one and turning something off
 * for it are two presses rather than one impossible one. */
const pending = new Map();

/* The pictures, by the thing they are of. They are asked for as rows
 * come into view rather than with the list, because the list is three
 * hundred rows and a screenful is twenty -- so what is kept here is
 * whatever has been looked at, which is the right amount. A thing with
 * no picture is remembered as having none, or it would be asked about
 * again every time it scrolled past. */
const pictures = new Map();

/** The key a picture is kept under, which is what was asked for. */
function nameOf(wanted) {
  return JSON.stringify(wanted);
}

const cameos = {
  get: (wanted) => pictures.get(nameOf(wanted)) || '',
  load: async (wanted) => {
    const asking = wanted.filter((one) => !pictures.has(nameOf(one)));
    if (asking.length) {
      let answer;
      try {
        answer = await call('campaign.cameos', {
          units: asking.filter((one) => one.unit).map((one) => one.unit),
          powers: asking.filter((one) => one.power).map((one) => one.power),
        });
      } catch {
        // The pictures are not the point of the screen. A list that
        // still says what everything is called is a list that works.
        return null;
      }
      for (const one of asking) {
        const found = one.unit
          ? answer.units[one.unit]
          : answer.powers[one.power];
        pictures.set(nameOf(one), found || '');
      }
    }
    return new Map(wanted.map((one) => [nameOf(one), cameos.get(one)]));
  },
};

const tools = {
  onChange: (name, value) => act('campaign.use_setting', { name, value }),
  catalogues,
  queries,
  opens,
  pending,
  cameos,
  refresh,
};

/**
 * A button that asks once.
 *
 * Generating replaces the run that is standing, and there are no dialogs
 * on these screens -- so the button becomes the question and the second
 * press is the answer, the same bargain the roguelike makes before
 * ending a run. Asked only when there is a run to lose: a first run is
 * not a decision anybody needs protecting from.
 */
function generateButton(standing) {
  let asked = !standing;
  const node = button('Generate the run', {
    variant: 'primary',
    onClick: async () => {
      if (!asked) {
        asked = true;
        node.textContent = 'Replace the run in progress?';
        return null;
      }
      return act('campaign.generate');
    },
  });
  return node;
}

async function render(root) {
  const answer = await call('campaign.settings');
  await Promise.all(searchesIn(answer.sections).map(fetchCatalogue));
  root.replaceChildren(
    section('The next run', [
      notice(
        answer.mode
          ? `These are ${answer.mode}'s settings. Generate the run they `
            + 'describe at the bottom of this screen, then play it on the '
            + 'Run tab.'
          : 'The campaign settings, shared by Classic, Mission List and Grid.',
      ),
      // Why the seed box is empty when a run is standing. The classic
      // window empties it for the same reason and says nothing; here
      // there is room to say it.
      answer.generated_seed
        ? notice(
          `A seed is standing: ${answer.generated_seed}. The box below is `
          + 'empty on purpose, so that generating again does not replay '
          + 'the run in progress.',
        )
        : null,
      ...settingsSections(answer.sections, tools),
      panel('Generate', {
        body: 'Deals the missions, plans the rewards and writes the run '
          + 'down. The Run tab is where it is then played.',
        footer: [
          el('span', {
            class: 'muted',
            text: answer.generated_seed
              ? 'This replaces the run in progress.'
              : 'No run is standing.',
          }),
          generateButton(answer.generated_seed),
        ],
      }),
    ]),
  );
}

register('campaign', render);
