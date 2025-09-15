# pointsystem.py

def merge_duplicate_bosses(bosses: dict) -> dict:
    """
    Combine duplicate or composite bosses so everything counts correctly.
    """
    merged = bosses.copy()
    if "calvar'ion" in bosses or "vet'ion" in bosses:
        merged["calvar'ion & vet'ion"] = bosses.get("calvar'ion", 0) + bosses.get("vet'ion", 0)
        merged.pop("calvar'ion", None)
        merged.pop("vet'ion", None)
    if "spindel" in bosses or "venenatis" in bosses:
        merged["spindel & venenatis"] = bosses.get("spindel", 0) + bosses.get("venenatis", 0)
        merged.pop("spindel", None)
        merged.pop("venenatis", None)
    return merged


def calculate_points(mapped: dict) -> int:
    points = 0

    # === SKILLS ===
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

    # === BOSSES & RAIDS ===
    boss_points = {
        "barrows": 50, "scurrius": 50, "giant mole": 50, "deranged archaeologist": 50,
        "moons of peril": 75, "kalphite queen": 100, "the hueycoatl": 150,
        "corporeal beast": 200, "dagannoth supreme": 50, "dagannoth rex": 50, "dagannoth prime": 50,
        "kree'arra": 100, "commander zilyana": 100, "general graardor": 100, "k'ril tsutsaroth": 100,
        "nex": 200, "chaos fanatic": 40, "crazy archaeologist": 50, "scropia": 60,
        "king black dragon": 100, "chaos elemental": 80, "calvar'ion & vet'ion": 75, "spindel & venenatis": 70,
        "artio & callisto": 65, "obor": 50, "bryophyta": 50, "amoxliatl": 70, "royal titans": 90,
        "doom of makhaiotl": 120, "zulrah": 100, "vorkath": 125, "phantom muspah": 100,
        "the nightmare": 200, "phosani's nightmare": 200, "yama": 150, "sarachnis": 90,
        "duke sucellus": 100, "the leviathan": 120, "the wisperer": 120, "vardorvis": 150,
        "the mimic": 75, "hespori": 100, "skotizo": 120,
        "grotesque guardians": 100, "abyssal sire": 100, "kraken": 80, "cerberus": 120,
        "araxxor": 150, "thermonuclear": 200, "alchemical hydra": 175,
        "crystalline hunleff": 50, "corrupted hunleff": 75, "tztok-jad": 100, "tzkal-zuk": 150,
        "sol heredit": 125, "tempoross": 50, "wintertodt": 50, "zalcano": 75,
        # Raids
        "cox normal": 75, "toa normal": 75, "tob normal": 75,
        "cox challenge mode": 150, "toa expert 300-450 inv": 100,
        "toa expert 450+ inv": 150, "tob hard mode": 175,
    }

    merged_bosses = merge_duplicate_bosses(mapped.get("bosses", {}))
    for boss, pts_per_kc in boss_points.items():
        kc = merged_bosses.get(boss, 0)
        if boss.startswith("cox") or boss.startswith("toa") or boss.startswith("tob"):
            points += (kc // 10) * pts_per_kc
        else:
            points += (kc // 100) * pts_per_kc

    # === DIARIES ===
    diaries = mapped.get("diaries", {})
    if diaries.get("easy", 0) >= 1: points += 5
    if diaries.get("medium", 0) >= 1: points += 10
    if diaries.get("hard", 0) >= 1: points += 20
    if diaries.get("elite", 0) >= 1: points += 40
    if diaries.get("all_completed"): points += 50

    # === ACHIEVEMENTS ===
    achievements = mapped.get("achievements", {})
    if achievements.get("quest_cape"): points += 75
    if achievements.get("music_cape"): points += 25
    if achievements.get("diary_cape"): points += 100
    if achievements.get("max_cape"): points += 300
    if achievements.get("infernal_cape"): points += 200

    # === PETS ===
    pets = mapped.get("pets", {})
    points += pets.get("skilling", 0) * 25
    points += pets.get("boss", 0) * 50
    points += pets.get("raids", 0) * 75

    # === EVENTS ===
    events = mapped.get("events", {})
    points += events.get("pvm_participations", 0) * 10
    points += events.get("event_wins", 0) * 15

    # === DONATIONS ===
    donations = mapped.get("donations", 0)
    if 1 <= donations < 25_000_000:
        points += 10
    elif 25_000_000 <= donations < 50_000_000:
        points += 20
    elif 50_000_000 <= donations < 100_000_000:
        points += 40
    elif 100_000_000 <= donations < 200_000_000:
        points += 80
    elif donations >= 200_000_000:
        points += 150

    return points
