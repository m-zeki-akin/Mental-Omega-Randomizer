/* The campaign run standing, as far as it has got -- and the playing of it.
 *
 * A player opens the launcher to ask two things about a run they are in
 * the middle of: which mission is next, and how much is behind them. Both
 * were only answerable by opening the classic window, which is a lot of
 * window for a question.
 *
 * Then to play one. A mission is not launched and forgotten: the game
 * says what it did through its own log while it is still up, and every
 * objective read out of it is a reward the run pays. A window watched
 * that on a timer. Here the screen asks, on the same timer, which is why
 * the table keeps counting up while the game is open. */

import { act, call, refresh, register, status } from '../app.js';
import {
  button, el, notice, panel, section, stats, table,
} from '../components/index.js';

const COLUMNS = [
  { key: 'name', label: 'Mission' },
  { key: 'side', label: 'Side' },
  { key: 'progress', label: 'Rewards' },
  { key: 'standing', label: '' },
  { key: 'play', label: '' },
];

/** What one mission is, in a word. */
function standing(mission) {
  if (mission.complete) return 'Finished';
  if (mission.started) return 'Started';
  if (!mission.installed) return 'Not installed';
  return mission.unlocked ? 'Open' : 'Locked';
}

function missionRows(run) {
  return run.missions.map((mission) => ({
    ...mission,
    progress: mission.total ? `${mission.done} / ${mission.total}` : '--',
    standing: standing(mission),
    next: mission.code === run.next,
  }));
}

/* Every open mission is offered, not only the next one: an ordered run
 * has one open at a time but a board has several, and the run itself is
 * what decides that. A finished one is offered too, because replaying a
 * mission has always been allowed. */
function playButton(row, busy) {
  if (!row.installed || !row.unlocked) return null;
  return button(row.complete ? 'Play again' : 'Fight', {
    variant: row.next ? 'primary' : 'quiet',
    // One game at a time. The button stays where it is rather than
    // disappearing while a mission is up, so the table does not change
    // shape underneath somebody reading it.
    disabled: busy,
    title: busy ? 'A mission is being played' : null,
    onClick: async () => {
      status(`Preparing ${row.name}…`);
      const started = await act('campaign.launch', { code: row.code });
      if (started) status(`${started.name} is starting.`);
    },
  });
}

/* Whether a game is up is one fact about the whole table, not about any
 * row in it, so it is closed over rather than written onto every row. */
function cellsWhile(busy) {
  return (row, key) => cell(row, key, busy);
}

/* A locked mission is still worth listing -- the order is the run -- but
 * it is not what the eye should land on. The one that is next is. */
function cell(row, key, busy) {
  if (key === 'play') return playButton(row, busy);
  const text = String(row[key] ?? '');
  if (key === 'name' && row.next) {
    return el('div', {}, [
      el('span', { text }),
      el('span', { class: 'pill', text: 'next' }),
    ]);
  }
  const faint = !row.unlocked && !row.complete;
  return el('span', { class: faint ? 'muted' : null, text });
}

function header(run) {
  const lines = [
    `Seed ${run.seed}`,
    // Named as what it was made as, because that is not always what the
    // launcher is set to now. A run keeps the order it was dealt.
    run.mode ? `Made as ${run.mode}` : '',
    run.campaign,
    `${run.won} of ${run.goal} missions finished`,
    `${run.rewards} rewards earned`,
  ];
  return panel('This run', { children: [stats(lines.filter(Boolean))] });
}

/* While a mission is up the screen keeps asking, and not only to know
 * when it ends: the reading is what records each objective as the game
 * reports it, so a screen that stopped asking would be a run that stopped
 * being paid. */
const POLL_MS = 2000;
let polling = null;

function watch() {
  if (polling) return;
  polling = setInterval(async () => {
    let session;
    try {
      session = await call('campaign.session');
    } catch {
      return;
    }
    if (session.playing) {
      // Redrawn rather than left alone: what the game has just reported
      // is in the run now, and the table is where that shows.
      await refresh();
      return;
    }
    clearInterval(polling);
    polling = null;
    await refresh();
    if (session.finished) status(session.finished.message || '');
  }, POLL_MS);
}

function playingNotice(session) {
  const done = session.total
    ? ` ${session.done} of ${session.total} recorded so far.`
    : '';
  return notice(
    `${session.code} is being played.${done} This screen keeps reading `
    + 'the game as it goes; it comes back when the game closes.',
  );
}

async function render(root) {
  const answer = await call('campaign.run');
  const run = answer.run;
  if (!run) {
    root.replaceChildren(section('This run', notice(
      answer.refused
      || 'No run has been generated yet. Set one up on the Setup tab, '
      + 'then generate it there.',
    )));
    return;
  }
  const session = await call('campaign.session');
  const parts = [section(null, header(run))];
  if (session.playing) {
    watch();
    parts.push(section(null, playingNotice(session)));
  }
  if (run.standing_mode && run.mode && run.standing_mode !== run.mode) {
    // Worth saying plainly rather than leaving two words to contradict
    // each other: the control above says one mode and the run says
    // another, and both are true.
    parts.push(section(null, notice(
      `The launcher is set to ${run.standing_mode}, and this run was made `
      + `as ${run.mode}. It keeps the order it was dealt; generating a `
      + 'new run is what changes that.',
    )));
  }
  if (run.finished) {
    parts.push(section(null, notice(
      'This run is finished. Generate another to keep playing.',
    )));
  }
  parts.push(section('Missions', table(COLUMNS, missionRows(run), {
    cell: cellsWhile(Boolean(session.playing)),
  })));
  root.replaceChildren(...parts);
}

register('run', render);
