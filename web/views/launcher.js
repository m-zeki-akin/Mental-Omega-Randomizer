/* The launcher itself, rather than anything it is playing.
 *
 * Two settings so far, and what they have in common is that neither
 * belongs to a mode: which interface opens, and whether either is drawn
 * light or dark. A mode's own settings belong on that mode's screens. */

import { act, applyTheme, call, register } from '../app.js';
import { button, el, notice, panel, pill, section } from '../components/index.js';

function interfacePanel(appearance) {
  return panel('Interface', [
    el('div', { class: 'card__body', text:
      'Two interfaces read the same runs and the same settings. This one '
      + 'draws the Skirmish Shop mode; the classic window draws every '
      + 'mode, and is what a start opens unless you say otherwise.' }),
    el('div', { class: 'card__footer' }, [
      el('span', { class: 'muted', text: appearance.new
        ? 'This interface opens at start.'
        : 'The classic window opens at start.' }),
      button(
        appearance.new ? 'Open the classic window at start' : 'Open this one at start',
        {
          variant: 'quiet',
          onClick: () => act('launcher.use_interface', {
            name: appearance.new ? 'classic' : 'new',
          }),
        },
      ),
    ]),
  ]);
}

function themePanel(appearance) {
  return panel('Theme', [
    el('div', { class: 'card__body', text:
      'One setting for both interfaces: the classic window calls it dark '
      + 'mode.' }),
    el('div', { class: 'card__footer' }, [
      el('span', { class: 'muted' }, [
        'Drawn ', pill(appearance.theme, 'accent'), ' now.',
      ]),
      button(appearance.dark ? 'Go light' : 'Go dark', {
        variant: 'quiet',
        onClick: async () => {
          const wanted = appearance.dark ? 'light' : 'dark';
          if (await act('launcher.use_theme', { name: wanted })) {
            await applyTheme(wanted);
          }
        },
      }),
    ]),
  ]);
}

function classicSeed(seed) {
  if (!seed || !seed.seed) return null;
  return notice(
    `The classic window has a ${seed.mode || 'campaign'} seed standing: `
    + `${seed.seed}. Opening it there carries on from that.`,
  );
}

async function render(root) {
  const appearance = await call('launcher.appearance');
  const modes = await call('launcher.modes');
  root.replaceChildren(
    section('Launcher', [interfacePanel(appearance), themePanel(appearance)]),
    section('Elsewhere', [
      classicSeed(modes.campaign_seed)
      || notice('No campaign seed has been generated.'),
    ]),
  );
}

register('launcher', render);
