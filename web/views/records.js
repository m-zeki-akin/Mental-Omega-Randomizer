/* Where a roguelike run ends up: the skirmish board, and what every
 * Shop run so far has left behind. One screen for the pair, because a
 * run with lives ends somewhere whichever kind it was. */

import { call, refresh, register } from '../app.js';
import { notice, section, stats, table } from '../components/index.js';

const COLUMNS = [
  { key: 'reached', label: 'Reached' },
  { key: 'army', label: 'Army' },
  { key: 'outcome', label: 'Outcome' },
  { key: 'battles', label: 'Battles' },
  { key: 'kills', label: 'Kills' },
  { key: 'score', label: 'Score' },
  { key: 'ore', label: 'Ore earned' },
  { key: 'ended', label: 'Ended' },
];

/* Which run is being looked at, by its own id rather than by where it sat
 * in the list. The board is kept furthest first, so one run ending moves
 * every row below it -- and a remembered position would then be pointing
 * at somebody else's run. */
let selected = null;

/** The campaign shop's lifetime, as the lines the profile keeps. */
function shopLines(profile) {
  if (!profile) return ['Nothing is known about Shop Mode yet.'];
  return [
    `Runs started: ${profile.runs_started}`,
    `Runs completed: ${profile.runs_completed}`,
    `Missions completed: ${profile.missions_completed}`,
    `Gems in hand: ${profile.meta_coins}`,
    `Permanent units: ${(profile.units || []).length}`,
    `Salvaged Ore carried: ${profile.salvaged}`,
  ];
}

function skirmishBoard(entries) {
  if (!entries.length) return [notice('No skirmish run has ended yet.')];
  const rows = entries.map((entry) => {
    const row = { run_id: entry.run_id };
    COLUMNS.forEach((column, index) => {
      row[column.key] = entry.row[index];
    });
    return row;
  });
  const at = rows.findIndex((row) => row.run_id === selected);
  const chosen = at < 0 ? null : entries[at];
  return [
    table(COLUMNS, rows, {
      selected: at < 0 ? null : at,
      onSelect: (row) => {
        selected = row.run_id;
        refresh();
      },
    }),
    chosen
      ? section(`${chosen.reached} — seed ${chosen.seed}`,
        stats(chosen.stat_lines))
      : notice('Select a run to see what it did.'),
  ];
}

async function render(root) {
  const [entries, profile] = await Promise.all([
    call('skirmish.board'),
    call('shop.profile').catch(() => null),
  ]);
  root.replaceChildren(
    section('Skirmish runs', skirmishBoard(entries)),
    section('Shop Mode', stats(shopLines(profile))),
  );
}

register('records', render);
