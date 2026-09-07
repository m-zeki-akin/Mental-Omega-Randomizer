/* What the run has handed over, and what it still might.
 *
 * The Run screen counts: two of eight missions, sixteen rewards. That is
 * the question a player asks before playing, and this is the one they ask
 * after -- what were those sixteen, and what is the next one likely to
 * be. A number cannot answer it and a list of names barely can, because
 * what a player remembers about a unit is its icon.
 *
 * Everything is listed, including what this run will never offer. That is
 * not padding: a seed that has left every Soviet aircraft out is a fact
 * about the run, and a list showing only what is still reachable has no
 * way to say it. */

import { call, register } from '../app.js';
import { cameos } from '../cameos.js';
import { el, notice, panel, pill, section, stats } from '../components/index.js';

/* The four states, in the order a player reads them: what is in hand,
 * what could come next, what is behind something, and what this run was
 * never going to offer. */
const STANDINGS = [
  { key: 'unlocked', label: 'In hand' },
  { key: 'available', label: 'Could come next' },
  { key: 'locked', label: 'Behind something' },
  { key: 'unavailable', label: 'Not in this run' },
];
const NAMED = new Map(STANDINGS.map((one) => [one.key, one.label]));

/* Which side is being looked at, and whether the run's own unreachable
 * half is drawn. Kept across a redraw, like every other choice a screen
 * makes about itself. */
let showing = '';
let showAll = false;

function tile(entry) {
  const box = el('span', { class: 'cameo cameo--tile' });
  const held = cameos.get(entry.cameo);
  if (held) box.append(el('img', { src: held, alt: '' }));
  else if (entry.cameo && (entry.cameo.unit || entry.cameo.power)) {
    box.dataset.wanted = JSON.stringify(entry.cameo);
  }
  return el('div', {
    class: `unlock unlock--${entry.standing}`,
    title: entry.note
      ? `${entry.label} — ${NAMED.get(entry.standing)}. ${entry.note}`
      : `${entry.label} — ${NAMED.get(entry.standing)}`,
  }, [box, el('span', { class: 'unlock__name', text: entry.label })]);
}

/* Ask for the pictures of the tiles somebody can see, and put each one
 * into the tile that wanted it -- rather than drawing the screen again,
 * which would lose where they had scrolled to. */
let watcher = null;

function watch(root) {
  if (typeof IntersectionObserver !== 'function') return;
  // Picking a side draws the screen again, and the tiles that were being
  // watched are gone. A watcher still holding them would keep asking for
  // pictures nothing is going to show.
  if (watcher) watcher.disconnect();
  let waiting = [];
  let asked = null;
  const settle = async () => {
    asked = null;
    const boxes = waiting;
    waiting = [];
    const found = await cameos.load(
      boxes.map((box) => JSON.parse(box.dataset.wanted)),
    );
    if (!found) return;
    for (const box of boxes) {
      const uri = found.get(box.dataset.wanted);
      if (!uri || !box.isConnected) continue;
      delete box.dataset.wanted;
      box.replaceChildren(el('img', { src: uri, alt: '' }));
    }
  };
  watcher = new IntersectionObserver((seen) => {
    for (const one of seen) {
      if (!one.isIntersecting || !one.target.dataset.wanted) continue;
      watcher.unobserve(one.target);
      waiting.push(one.target);
    }
    if (waiting.length && asked === null) asked = setTimeout(settle, 60);
  });
  for (const box of root.querySelectorAll('.cameo[data-wanted]')) {
    watcher.observe(box);
  }
}

function sideTabs(factions, onPick) {
  return el('div', { class: 'row' }, factions.map((faction) => el('button', {
    class: faction === showing ? 'button button--primary' : 'button',
    type: 'button',
    text: faction,
    onClick: () => onPick(faction),
  })));
}

function header(answer) {
  const { counts, run } = answer;
  return panel('This run', {
    children: [stats([
      `Seed ${run.seed}`,
      run.mode ? `Made as ${run.mode}` : '',
      `${run.earned} rewards earned`,
      ...STANDINGS.map((one) => `${NAMED.get(one.key)}: ${counts[one.key]}`),
    ].filter(Boolean))],
  });
}

function groupsOf(entries) {
  const groups = [];
  for (const entry of entries) {
    const last = groups[groups.length - 1];
    if (last && last.name === entry.group) last.entries.push(entry);
    else groups.push({ name: entry.group, entries: [entry] });
  }
  return groups;
}

async function render(root) {
  const answer = await call('campaign.unlocks');
  if (!answer.run) {
    root.replaceChildren(section('Unlocks', notice(
      'No run has been generated yet. Set one up on the Setup tab, then '
      + 'generate it there.',
    )));
    return;
  }
  const { factions, entries } = answer;
  if (!factions.includes(showing)) showing = factions[0] || '';
  const mine = entries.filter((entry) => (
    entry.faction === showing
    && (showAll || entry.standing !== 'unavailable')
  ));
  const hidden = entries.filter((entry) => (
    entry.faction === showing && entry.standing === 'unavailable'
  )).length;
  const parts = [
    section(null, header(answer)),
    section('Side', sideTabs(factions, (faction) => {
      showing = faction;
      return render(root);
    })),
  ];
  if (hidden) {
    parts.push(section(null, el('div', { class: 'row' }, [
      el('span', {
        class: 'muted',
        text: showAll
          ? `Showing all of ${showing}, including what this run cannot offer.`
          : `${hidden} more this run was never going to offer.`,
      }),
      el('button', {
        class: 'button button--quiet',
        type: 'button',
        text: showAll ? 'Hide those' : 'Show those too',
        onClick: () => {
          showAll = !showAll;
          return render(root);
        },
      }),
    ])));
  }
  for (const group of groupsOf(mine)) {
    parts.push(section(group.name || 'Other', [
      el('div', { class: 'row' }, STANDINGS.map((one) => {
        const many = group.entries.filter(
          (entry) => entry.standing === one.key,
        ).length;
        return many ? pill(`${one.label}: ${many}`) : null;
      }).filter(Boolean)),
      el('div', { class: 'unlocks' }, group.entries.map(tile)),
    ]));
  }
  if (!mine.length) {
    parts.push(section(null, notice(
      `Nothing of ${showing} is in this run.`,
    )));
  }
  root.replaceChildren(...parts);
  watch(root);
}

register('unlocks', render);
