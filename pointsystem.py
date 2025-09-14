# pointsystem.py

def calculate_points(mapped: dict) -> int:
    points = 0

    # === TOTAL LEVELS ===
    total_level = mapped["skills"]["total_level"]
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

    # === BOSSES (per 100 KC) ===
    bosses = mapped["bosses"]
    points += (bosses.get("barrows", 0) // 100) * 10
    points += (bosses.get("zulrah", 0) // 100) * 25
    points += (bosses.get("vorkath", 0) // 100) * 30
    points += (bosses.get("gwd", 0) // 100) * 40
    points += (bosses.get("wildy", 0) // 100) * 50

    # === First-time boss kills ===
    points += mapped.get("first_time_kills", 0) * 10

    # === Jad & Zuk ===
    points += bosses.get("jad", 0) * 25
    points += bosses.get("zuk", 0) * 150

    # === RAIDS ===
    points += bosses.get("cox", 0) * 75
    points += bosses.get("tob", 0) * 75
    points += bosses.get("toa", 0) * 75

    # === DIARIES ===
    diaries = mapped["diaries"]
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
    achievements = mapped["achievements"]
    if achievements.get("quest_cape"):
        points += 75
    if achievements.get("music_cape"):
        points += 25
    if achievements.get("diary_cape"):
        points += 100
    if achievements.get("max_cape"):
        points += 300

    # === SKILLS ===
    skills = mapped["skills"]
    if skills.get("first_99"):
        points += 50
    points += skills.get("extra_99s", 0) * 25
    if skills.get("total_level") >= 2277:
        points += 200
    if achievements.get("max_cape"):
        points += 300

    # === PETS ===
    pets = mapped["pets"]
    points += pets.get("skilling", 0) * 25
    points += pets.get("boss", 0) * 50
    points += pets.get("raids", 0) * 75

    # === EVENTS (manual, via admin) ===
    events = mapped.get("events", {})
    points += events.get("pvm_participations", 0) * 10
    points += events.get("event_wins", 0) * 15

    # === DONATIONS (manual, via admin) ===
    donations = mapped.get("donations", 0)
    if 1 <= donations < 25:
        points += 10
    elif 25 <= donations < 50:
        points += 20
    elif 50 <= donations < 100:
        points += 40
    elif 100 <= donations < 200:
        points += 80
    elif donations >= 200:
        points += 150

    return points
