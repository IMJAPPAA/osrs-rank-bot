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

def calculate_points(mapped: dict, boss_kc_at_link: dict | None = None) -> int:
    points = 0
    boss_kc_at_link = boss_kc_at_link or {}

    # SKILLS
    skills = mapped.get("skills", {})
    total_level = skills.get("total_level", 0)
    combat_level = skills.get("combat_level", 0)
    if total_level < 1000:
        points += 25
    elif total_level < 1500:
        points += 30
    elif total_level < 1750:
        points += 35
    elif total_level < 2000:
        points += 40
    elif total_level < 2200:
        points += 45
    else:
        points += 50
    if skills.get("first_99"):
        points += 50
    points += skills.get("extra_99s", 0) * 25
    if total_level >= 2277:
        points += 200

    # BOSSES & RAIDS
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
    for boss, pts_per_kc in boss_points.items():
        current_kc = merged_bosses.get(boss, 0)
        start_kc = boss_kc_at_link.get(boss, 0)
        kc_delta = max(0, current_kc - start_kc)
        if boss.startswith("cox") or boss.startswith("toa") or boss.startswith("tob"):
            points += (kc_delta // 10) * pts_per_kc
        else:
            points += (kc_delta // 100) * pts_per_kc

    # DIARIES
    diaries = mapped.get("diaries", {})
    if diaries.get("easy", 0) >= 1: points += 5
    if diaries.get("medium", 0) >= 1: points += 10
    if diaries.get("hard", 0) >= 1: points += 20
    if diaries.get("elite", 0) >= 1: points += 40
    if diaries.get("all_completed"): points += 50

    # ACHIEVEMENTS
    ach = mapped.get("achievements", {})
    if ach.get("quest_cape"): points += 75
    if ach.get("music_cape"): points += 25
    if ach.get("diary_cape"): points += 100
    if ach.get("max_cape"): points += 300
    if ach.get("infernal_cape"): points += 200

    # PETS
    pets = mapped.get("pets", {})
    points += pets.get("skilling", 0) * 25
    points += pets.get("boss", 0) * 50
    points += pets.get("raids", 0) * 75

    return points
