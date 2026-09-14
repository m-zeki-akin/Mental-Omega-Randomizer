/* The launcher itself, rather than anything it is playing.
 *
 * What everything here has in common is that none of it belongs to a
 * mode: whether the launcher is drawn light or dark, and how a mission
 * is written out looking and sounding. A mode's own settings belong on
 * that mode's screens.
 *
 * The last of those is on this screen and not on a run's setup for a
 * reason worth keeping: two runs made from the same seed play the same
 * however those three are set. They change what the map is written with,
 * not what the run is. */

import { act, applyTheme, call, register } from '../app.js';
import {
  button, el, field, panel, pill, section, select, toggle,
} from '../components/index.js';

function themePanel(appearance) {
  return panel('Theme', {
    body: 'Kept between starts, the way everything on this screen is.',
    footer: [
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
    ],
  });
}

function lookPanel(mission) {
  const change = (name, value) => act('launcher.use_mission_look', {
    name, value,
  });
  const choice = (name, label) => field(label, select(
    mission[name].choices.map((one) => ({ value: one, label: one })),
    { value: mission[name].value, onChange: (value) => change(name, value) },
  ));
  return panel('In the game', {
    body: 'How a mission is written out. None of it changes what a run '
      + 'is: the same seed deals the same missions and the same rewards '
      + 'however these are set.',
    children: [
      choice('player_color', 'Your colour'),
      choice('eva_voice', 'Whose voice reads the briefing'),
      field('Shuffle the other house colours', toggle({
        value: mission.rainbowizer.value,
        onChange: (value) => change('rainbowizer', value),
      })),
    ],
  });
}

async function render(root) {
  const appearance = await call('launcher.appearance');
  root.replaceChildren(
    section('Launcher', themePanel(appearance)),
    section('Missions', lookPanel(appearance.mission)),
  );
}

register('launcher', render);
