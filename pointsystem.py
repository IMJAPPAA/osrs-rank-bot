# pointsystem.py

def merge_duplicate_bosses(bosses: dict) -> dict:
    """
    Combineert KC's van dubbele of samengestelde bosses zodat alles correct telt.
    Bijvoorbeeld:
        - "corporeal beast" in meerdere categorieën
        - "calvar'ion & vet'ion" als combinatie van individuele entries
    """
    merged = bosses.copy()

    # Voor combinaties zoals Calvar'ion & Vet'ion
    if "calvar'ion" in bosses or "vet'ion" in bosses:
        merged["calvar'ion & vet'ion"] = bosses.get("calvar'ion", 0) + bosses.get("vet'ion", 0)
        merged.pop("calvar'ion", None)
        merged.pop("vet'ion", None)

    if "spindel" in bosses or "venenatis" in bosses:
        merged["spindel & venenatis"] = bosses.get("spindel", 0) + bosses.get("venenatis", 0)
        merged.pop("spindel", None)
        merged.pop("venenatis", None)

    # Dubbele entries van corp beast en hespori al samengevoegd in boss_points
    # Zorg dat geen dubbele keys overblijven
    return merged


def calculate_points(mapped: dict) -> int:
    points = 0

    # === SKILLS ===
    total_level = mapped["skills"].get("total_level", 0)
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

    if mapped["skills"].get("first_99"):
        points += 50
    points += mapped["skills"].get("extra_99s", 0) * 25
    if total_level >= 2277:
        points += 200

    # === BOSSES ===
    boss_points = {
        # 🟦 Early Game Bosses
        "barrows": 50,
        "scurrius": 50,
        "giant mole": 50,
        "deranged archaeologist": 50,
        "moons of peril": 75,
        "kalphite queen": 100,
        "the hueycoatl": 150,
        "corporeal beast": 200,
        "dagannoth supreme": 50,
        "dagannoth rex": 50,
        "dagannoth prime": 50,

        # 🟩 GWD Bosses
        "kree'arra": 100,
        "commander zilyana": 100,
        "general graardor": 100,
        "k'ril tsutsaroth": 100,
        "nex": 200,

        # 🟨 Wilderness Bosses
        "chaos fanatic": 40,
        "crazy archaeologist": 50,
        "scropia": 60,
        "king black dragon": 100,
        "chaos elemental": 80,
        "calvar'ion & vet'ion": 75,
        "spindel & venenatis": 70,
        "artio & callisto": 65,

        # 🟪 Instanced Bosses
        "obor": 50,
        "bryophyta": 50,
        "amoxliatl": 70,
        "royal titans": 90,
        "doom of makhaiotl": 120,
        "zulrah": 100,
        "vorkath": 125,
        "phantom muspah": 100,
        "the nightmare": 200,
        "phosani's nightmare": 200,
        "yama": 150,
        "sarachnis": 90,

        # 🟧 Forgotten Four
        "duke sucellus": 100,
        "the leviathan": 120,
        "the wisperer": 120,
        "vardorvis": 150,

        # 🟥 Sporadic Bosses
        "the mimic": 75,
        "hespori": 100,
        "skotizo": 120,

        # 🟫 Slayer Bosses
        "grotesque guardians": 100,
        "abyssal sire": 100,
        "kraken": 80,
        "cerberus": 120,
        "araxxor": 150,
        "thermonuclear": 200,
        "alchemical hydra": 175,

        # 🟦 Minigame Bosses
        "crystalline hunleff": 50,
        "corrupted hunleff": 75,
        "tztok-jad": 100,
        "tzkal-zuk": 150,
        "sol heredit": 125,

        # 🟩 Skilling Bosses
        "tempoross": 50,
        "wintertodt": 50,
        "zalcano": 75,

        # 🟨 Raids (Normal Mode)
        "cox normal": 75,
        "toa normal": 75,
        "tob normal": 75,

        # 🟪 Raids (Special/Hard Modes)
        "cox challenge mode": 150,
        "toa expert 300-450 inv": 100,
        "toa expert 450+ inv": 150,
        "tob hard mode": 175,
    }

    # Merge duplicate/split bosses
    merged_bosses = merge_duplicate_bosses(mapped.get("bosses", {}))

    # Voeg boss points toe
    for boss, pts_per_kc in boss_points.items():
        kc = merged_bosses.get(boss, 0)
        points += kc * pts_per_kc

    # === RAIDS ===
    raids = mapped.get("raids", {})
    points += raids.get("cox_normal", 0) * 75
    points += raids.get("toa_normal", 0) * 75
    points += raids.get("tob_normal", 0) * 75
    points += raids.get("cox_challenge_mode", 0) * 150
    points += raids.get("toa_expert_300-450_inv", 0) * 100
    points += raids.get("toa_expert_450+_inv", 0) * 150
    points += raids.get("tob_hard_mode", 0) * 175

    # === DIARIES ===
    diaries = mapped.get("diaries", {})
    if diaries.get("easy", 0) >= 1:
        points += 5
    if diaries.get("medium", 0) >= 1:
        points += 10
    if diaries.get("hard", 0) >= 1:
        points += 20
    if diaries.get("elite", 0) >= 1:
        points += 40
    if diaries.get("all_completed"):
        points += 50

    # === ACHIEVEMENTS ===
    achievements = mapped.get("achievements", {})
    if achievements.get("quest_cape"):
        points += 75
    if achievements.get("music_cape"):
        points += 25
    if achievements.get("diary_cape"):
        points += 100
    if achievements.get("max_cape"):
        points += 300

    # === PETS ===
    pets = mapped.get("pets", {})
    points += pets.get("skilling", 0) * 25
    points += pets.get("boss", 0) * 50
    points += pets.get("raids", 0) * 75

    # === EVENTS (manual, via admin) ===
    events = mapped.get("events", {})
    points += events.get("pvm_participations", 0) * 10
    points += events.get("event_wins", 0) * 15

    # === DONATIONS (manual, via admin) ===
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
