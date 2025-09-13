def calculate_points(data):
    points = 0

    # === Bosses (per 100 kills unless stated) ===
    b = data.get("bosses", {})
    points += (b.get("barrows", 0) // 100) * 10
    points += (b.get("zulrah", 0) // 100) * 25
    points += (b.get("vorkath", 0) // 100) * 30
    points += (b.get("gwd", 0) // 100) * 40
    points += (b.get("wildy", 0) // 100) * 50
    points += b.get("jad", 0) * 25   # per kill
    points += b.get("zuk", 0) * 150  # per clear
    points += (b.get("cox", 0) // 100) * 75
    points += (b.get("tob", 0) // 100) * 75
    points += (b.get("toa", 0) // 100) * 75
    points += data.get("first_time_kills", 0) * 10

    # === Diaries ===
    d = data.get("diaries", {})
    points += d.get("easy", 0) * 5
    points += d.get("medium", 0) * 10
    points += d.get("hard", 0) * 20
    points += d.get("elite", 0) * 40
    if d.get("all_completed", False):
        points += 50

    # === Achievements ===
    a = data.get("achievements", {})
    if a.get("quest_cape"): points += 75
    if a.get("music_cape"): points += 25
    if a.get("diary_cape"): points += 100
    if a.get("max_cape"): points += 300

    # === Skills ===
    s = data.get("skills", {})
    if s.get("first_99"): points += 50
    points += s.get("extra_99s", 0) * 25
    if s.get("total_level") == 2277: points += 200

    # If player is maxed (defensive check) and not flagged via achievements
    if s.get("total_level", 0) >= 2277 and a.get("max_cape") == False:
        points += 300

    # === Pets ===
    p = data.get("pets", {})
    points += p.get("skilling", 0) * 25
    points += p.get("boss", 0) * 50
    points += p.get("raids", 0) * 75

    # === Events ===
    e = data.get("events", {})
    points += e.get("pvm_participations", 0) * 10
    points += e.get("event_wins", 0) * 15

    # === Donations ===
    donation = data.get("donations", 0)
    if 1 <= donation < 25: points += 10
    elif 25 <= donation < 50: points += 20
    elif 50 <= donation < 100: points += 40
    elif 100 <= donation < 200: points += 80
    elif donation >= 200: points += 150

    return points
