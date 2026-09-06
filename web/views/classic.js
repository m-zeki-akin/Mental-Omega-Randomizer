/* A mode this interface does not draw yet.
 *
 * The mode control offers all five, because which mode the launcher is in
 * is one decision and hiding half of it would make the control lie. What
 * an unported mode gets is this: what it is, where it is played, and one
 * press to make the launcher open there next time. An empty panel would
 * be worse than the classic window; so would a mode that cannot be
 * selected at all.
 *
 * That press is also on the Launcher screen, on purpose and not by
 * accident: there it is the setting, here it is the way out of a mode
 * this interface cannot play. Removing either would cost more than the
 * duplication does. */

import { act, call, register } from '../app.js';
import { button, el, notice, panel, section } from '../components/index.js';

const ABOUT = {
  'Classic': 'Follows the installed campaign order, opening one mission '
    + 'at a time.',
  'Mission List': 'A randomized linear order through the campaign.',
  'Grid Mode': 'Randomized missions on a board where what you finish '
    + 'opens its neighbours.',
  'Shop Mode': 'The campaign roguelike: a run, a loadout, and a shop '
    + 'between missions.',
};

function modePanel(mode, seed, screens, kind) {
  const standing = seed && seed.seed && seed.mode === mode;
  // A mode with a screen of its own here has had part of it drawn, and
  // saying the classic window has everything would be false the moment
  // the player looked at the tab beside this one.
  const elsewhere = (screens || []).some(
    (screen) => screen.name !== 'classic' && screen.name !== 'launcher',
  );
  return panel(mode, {
    body: [
      // What the mode has in common with its siblings, then what makes it
      // this one. The control above offers them as one kind of game, so
      // the panel says what that kind is rather than leaving the grouping
      // to be guessed from a dropdown.
      kind && kind.description ? `${kind.name}: ${kind.description}` : '',
      ABOUT[mode] || '',
      elsewhere
        ? 'Its setup is on the tab beside this one; the run itself is '
          + 'played in the classic window, which draws the rest.'
        : 'This interface does not draw it yet. The classic window does, '
          + 'with every setting it has.',
      standing ? `A seed is standing for it: ${seed.seed}.` : '',
    ],
    footer: [
      el('span', { class: 'muted', text: 'Takes effect at the next start.' }),
      button('Open the classic window at start', {
        variant: 'primary',
        onClick: () => act('launcher.use_interface', { name: 'classic' }),
      }),
    ],
  });
}

async function render(root) {
  const modes = await call('launcher.modes');
  root.replaceChildren(
    section('Mode', modePanel(
      modes.current, modes.campaign_seed, modes.screens,
      (modes.families || []).find((kind) => kind.name === modes.family),
    )),
    section('Meanwhile', notice(
      'The Skirmish Shop mode is drawn here. Switch to it above to play '
      + 'without leaving this interface.',
    )),
  );
}

register('classic', render);
