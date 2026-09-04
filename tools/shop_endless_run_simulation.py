"""Drive the Shop run loop directly and assert the endless-run contract."""
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(r"C:\Users\mzeki\yedek\XCCUtilities\mo-randomizer\Mental-Omega-Randomizer")
sys.path.insert(0, str(ROOT))

from randomizer.shop.config import SHOP_CONFIG as CFG
from randomizer.shop.mission_modifiers import mission_modifier_for_run_offer
from randomizer.shop.missions import difficulty_stage, is_challenge_stage
from randomizer.shop.model import (
    MissionEconomyClass, MissionOffer, RunStatus, ShopProfile, ShopRun,
)
from randomizer.shop.transitions import (
    apply_mission_failure, apply_mission_victory, maximum_run_lives,
)

CODES = [f'M{i:03d}' for i in range(1, 200)]


def offers(n, start):
    return tuple(
        MissionOffer(mission_code=CODES[start + i],
                     economy_class=MissionEconomyClass.ACT_1)
        for i in range(n)
    )


def new_run(seed='sim-seed', endless=True, run_length=None):
    return ShopRun(
        run_id='run-1', seed=seed, status=RunStatus.ACTIVE, stage=1,
        run_length=run_length or CFG.run_length, run_coins=5,
        endless=endless, mission_offers=offers(3, 0),
    )


def play(profile, run, code, win, cursor):
    run = replace(run, selected_mission_code=code, mission_committed=True)
    if win:
        nxt = offers(CFG.mission_offer_count, cursor)
        last = not run.endless and run.stage == run.run_length
        t = apply_mission_victory(profile, run, code,
                                  next_offers=() if last else nxt)
        return t.profile, t.run, t.reward
    t = apply_mission_failure(run, code, profile=profile,
                              maximum_lives=maximum_run_lives(profile),
                              revival_offers=offers(CFG.mission_offer_count, cursor))
    return (t.profile or profile), t.run, None


failures = []


def check(label, ok):
    print(f'  {"PASS" if ok else "FAIL"}  {label}')
    if not ok:
        failures.append(label)


print(f'stage_length={CFG.stage_length}  starting_lives={CFG.starting_lives}  '
      f'AP run_length={CFG.run_length}')

# --- 1. endless run, all victories -----------------------------------------
print('\n[1] Sonsuz run, 12 zafer')
profile, run = ShopProfile(), new_run()
cursor, log = 10, []
for step in range(12):
    code = run.mission_offers[0].mission_code
    mod = mission_modifier_for_run_offer(run, run.mission_offers[0])
    was_challenge = bool(mod and mod.challenge)
    stage, tier = run.stage, difficulty_stage(run.stage)
    before_buffs = len(run.permanent_enemy_buff_ids)
    profile, run, reward = play(profile, run, code, True, cursor)
    cursor += 5
    log.append((stage, tier, was_challenge, reward.meta_coins,
                len(run.permanent_enemy_buff_ids) - before_buffs,
                len(run.completed_missions), reward.run_coins))
    print(f'   gorev {stage:>2} tier {tier}  challenge={str(was_challenge):5} '
          f'{reward.meta_coins:>3} Gem  +{log[-1][4]} buff  '
          f'gecmis={log[-1][5]}')

check('challenge tam olarak 3, 6, 9, 12de',
      [s for s, _t, c, *_ in log if c] == [3, 6, 9, 12])
check('her challenge zaferi 2 kalici buff verdi',
      all(b == 2 for _s, _t, c, _g, b, _h, _o in log if c))
check('challenge disi gorev buff vermedi',
      all(b == 0 for _s, _t, c, _g, b, _h, _o in log if not c))
check('tier atlayinca gorev gecmisi sifirlandi',
      [h for s, _t, _c, _g, _b, h, _o in log if s % 3 == 0] == [0, 0, 0, 0])
check('run hala aktif (sonsuz)', run.status is RunStatus.ACTIVE)
# Ore carries the stage multiplier; Gems deliberately do not, so permanent
# progression does not accelerate just because the run has run long.
challenge_ore = [item[6] for item in log if item[2]]
challenge_gems = [item[3] for item in log if item[2]]
check('challenge Ore geliri her tierde artti',
      challenge_ore == sorted(challenge_ore)
      and challenge_ore[0] < challenge_ore[-1])
# Boon modifiers still add a little Gem variance; what must not happen is
# Gems tracking the tier the way Ore does.
check('Gem geliri tier ile olceklenmedi',
      challenge_gems[-1] <= challenge_gems[0] * 1.25
      and challenge_ore[-1] >= challenge_ore[0] * 2)
check('challenge Gem >= normalin 2 kati',
      log[2][3] >= log[1][3] * 2)
check('toplam 8 kalici buff birikti', len(run.permanent_enemy_buff_ids) == 8)
check('buff stack tavani asilmadi',
      all(run.permanent_enemy_buff_ids.count(b) <= 5
          for b in set(run.permanent_enemy_buff_ids)))

# --- 2. lives ---------------------------------------------------------------
print('\n[2] 3 can: iki yenilgi hayatta birakir, ucuncu bitirir')
profile, run = ShopProfile(), new_run()
cursor = 60
for loss in range(1, 4):
    code = run.mission_offers[0].mission_code
    profile, run, _ = play(profile, run, code, False, cursor)
    cursor += 5
    print(f'   yenilgi {loss}: durum={run.status.name} '
          f'harcanan can={run.emergency_revivals_used}')
    check(f'{loss}. yenilgi -> ' + ('AKTIF' if loss < 3 else 'FAILED'),
          (run.status is RunStatus.ACTIVE) if loss < 3
          else (run.status is RunStatus.FAILED))

# --- 3. Extra Life upgrade --------------------------------------------------
print('\n[3] Extra Life yukseltmesi cani artiriyor')
upgraded = ShopProfile(permanent_upgrades={'emergency_revival': 2})
check('3 + 2 = 5 can', maximum_run_lives(upgraded) == 5)

# --- 4. determinism ---------------------------------------------------------
print('\n[4] Ayni seed ayni sonuc')


def sequence(seed):
    p, r = ShopProfile(), new_run(seed=seed)
    c, out = 10, []
    for _ in range(9):
        code = r.mission_offers[0].mission_code
        p, r, rew = play(p, r, code, True, c)
        c += 5
        out.append((rew.meta_coins, r.permanent_enemy_buff_ids))
    return out


check('ayni seed -> ayni dizi', sequence('seed-A') == sequence('seed-A'))
check('farkli seed -> farkli dizi', sequence('seed-A') != sequence('seed-B'))

# --- 5. Archipelago run stays finite ---------------------------------------
print('\n[5] AP run 9. gorevde biter')
profile, run = ShopProfile(), new_run(endless=False)
cursor = 10
for _ in range(CFG.run_length):
    code = run.mission_offers[0].mission_code
    profile, run, _ = play(profile, run, code, True, cursor)
    cursor += 5
check('AP run COMPLETED', run.status is RunStatus.COMPLETED)
check(f'{CFG.run_length} AP location kaydedildi',
      len(run.rewarded_victories) == CFG.run_length)
check('AP run son gorevi challenge sinirinda bitti',
      is_challenge_stage(CFG.run_length))

print('\n' + ('TUM KONTROLLER GECTI' if not failures
              else f'{len(failures)} KONTROL BASARISIZ: {failures}'))
sys.exit(1 if failures else 0)
