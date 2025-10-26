def merge_duplicate_bosses(bosses: dict) -> dict:
    merged = bosses.copy()
    if "calvarion" in bosses or "vetion" in bosses:
        merged["calvarion & vetion"] = bosses.get("calvarion", 0) + bosses.get("vetion", 0)
        merged.pop("calvarion", None)
        merged.pop("vetion", None)
    if "spindel" in bosses or "venenatis" in bosses:
        merged["spindel & venenatis"] = bosses.get("spindel", 0) + bosses.get("venenatis", 0)
        merged.pop("spindel", None)
        merged.pop("venenatis", None)
    return merged

def calculate_points(mapped: dict, baseline: dict | None = None) -> int:
    """
    Calculate points gained since baseline.
    If baseline is None, calculates all points from scratch.
    """
    baseline = baseline or {}
    points = 0

    # --- Skills ---
    skills = mapped.get("skills", {})
    base_skills = baseline.get("skills", {})

    total_level = skills.get("total_level", 0)
    base_total_level = base_skills.get("total_level", 0)

    # Base total_level points (delta only)
    total_level_points = 0
    if total_level > base_total_level:
        tl_delta = total_level - base_total_level
        if tl_delta > 0:
            thresholds = [(0,1000,25),(1000,1500,30),(1500,1750,35),(1750,2000,40),(2000,2200,45),(2200,float("inf"),50)]
            for lower, upper, pts in thresholds:
                if base_total_level < upper and total_level > lower:
                    total_level_points = pts
    points += total_level_points

    # 99s
    ninetynines = sum(1 for lvl in skills.values() if isinstance(lvl, int) and lvl >= 99)
    base_ninetynines = sum(1 for lvl in base_skills.values() if isinstance(lvl, int) and lvl >= 99)
    first_99 = ninetynines >= 1 and base_ninetynines < 1
    extra_99s = max(0, ninetynines - 1) - max(0, base_ninetynines - 1)
    if first_99: points += 50
    points += max(0, extra_99s) * 25
    if total_level >= 2277 and base_total_level < 2277:
        points += 200

    # --- Bosses & Raids ---
    boss_points = {
        "barrows_chests": 50, "scurrius": 50, "giant_mole": 50, "deranged_archaeologist": 50,
        "moons_of_peril": 75, "kalphite_queen": 100, "the_hueycoatl": 150,
        "corporeal_beast": 200, "dagannoth_supreme": 50, "dagannoth_rex": 50, "dagannoth_prime": 50,
        "kreearra": 100, "commander_zilyana": 100, "general_graardor": 100, "kril_tsutsaroth": 100,
        "nex": 200, "chaos_fanatic": 40, "crazy_archaeologist": 50, "scorpia": 60,
        "king_black_dragon": 100, "chaos_elemental": 80, "calvarion & vetion": 75, "spindel & venenatis": 70,
        "artio & callisto": 65, "obor": 50, "bryophyta": 50, "amoxliatl": 70, "the_royal_titans": 90,
        "doom_of_mokhaiotl": 120, "zulrah": 100, "vorkath": 125, "phantom_muspah": 100,
        "nightmare": 200, "phosanis_nightmare": 200, "yama": 150, "sarachnis": 90,
        "duke_sucellus": 100, "the_leviathan": 120, "the_whisperer": 120, "vardorvis": 150,
        "mimic": 75, "hespori": 100, "skotizo": 120,
        "grotesque_guardians": 100, "abyssal_sire": 100, "kraken": 80, "cerberus": 120,
        "araxxor": 150, "thermonuclear": 200, "alchemical_hydra": 175,
        "crystalline_hunleff": 50, "corrupted_hunleff": 75, "tztok_jad": 100, "tzkal_zuk": 150,
        "sol_heredit": 125, "tempoross": 50, "wintertodt": 50, "zalcano": 75,
        "cox_normal": 75, "toa_normal": 75, "tob_normal": 75,
        "cox_challenge_mode": 150, "toa_expert_300_450_inv": 100,
        "toa_expert_450_plus_inv": 150, "tob_hard_mode": 175,
    }

    merged_bosses = merge_duplicate_bosses(mapped.get("bosses", {}))
    base_bosses = merge_duplicate_bosses(baseline.get("bosses", {}))

    for boss, pts_per_kc in boss_points.items():
        current_kc = merged_bosses.get(boss, 0)
        start_kc = base_bosses.get(boss, 0)
        kc_delta = max(0, current_kc - start_kc)
        if boss.startswith("cox") or boss.startswith("toa") or boss.startswith("tob"):
            points += (kc_delta // 10) * pts_per_kc
        else:
            points += (kc_delta // 100) * pts_per_kc

    # --- Diaries ---
    diaries = mapped.get("diaries", {})
    base_diaries = baseline.get("diaries", {})
    if diaries.get("easy", 0) > base_diaries.get("easy", 0): points += 5
    if diaries.get("medium", 0) > base_diaries.get("medium", 0): points += 10
    if diaries.get("hard", 0) > base_diaries.get("hard", 0): points += 20
    if diaries.get("elite", 0) > base_diaries.get("elite", 0): points += 40
    if diaries.get("all_completed", False) and not base_diaries.get("all_completed", False): points += 50

    # --- Achievements ---
    ach = mapped.get("achievements", {})
    base_ach = baseline.get("achievements", {})
    for ach_key, pts in [("quest_cape",75),("music_cape",25),("diary_cape",100),("max_cape",300),("infernal_cape",200)]:
        if ach.get(ach_key, False) and not base_ach.get(ach_key, False):
            points += pts

    # --- Pets ---
    pets = mapped.get("pets", {})
    base_pets = baseline.get("pets", {})
    for pet_type, pts_per in [("skilling",25),("boss",50),("raids",75)]:
        delta = max(0, pets.get(pet_type,0) - base_pets.get(pet_type,0))
        points += delta * pts_per

    return points
