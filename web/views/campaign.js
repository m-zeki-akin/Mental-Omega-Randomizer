/* The campaign's setup: how the next run will be generated.
 *
 * One screen for Classic, Mission List and Grid, because they are the
 * same campaign in a different order and share all but three of their
 * settings. Which rows those three are is the launcher's to say, not this
 * screen's: it draws the sections it is given, in the order it is given
 * them, and a row it has never heard of would still be drawn.
 *
 * Generating the seed is still the classic window's, and the panel on the
 * tab beside this one says so. */

import { act, call, register } from '../app.js';
import { notice, section } from '../components/index.js';
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

const tools = {
  onChange: (name, value) => act('campaign.use_setting', { name, value }),
  catalogues,
  queries,
};

async function render(root) {
  const answer = await call('campaign.settings');
  await Promise.all(searchesIn(answer.sections).map(fetchCatalogue));
  root.replaceChildren(
    section('The next run', [
      notice(
        answer.mode
          ? `These are ${answer.mode}'s settings. Generating the seed they `
            + 'describe is still done in the classic window.'
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
    ]),
  );
}

register('campaign', render);
