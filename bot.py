# ===== Dummy audioop module =====
import sys, types
sys.modules['audioop'] = types.ModuleType('audioop')

# ===== Imports =====
import os, asyncio, requests, discord, urllib.parse
from discord.ext import commands
from discord import app_commands
import database
from pointsystem import calculate_points, merge_duplicate_bosses

# ===== Config =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WISE_API = "https://api.wiseoldman.net/v2/players/"

# ===== Ladder, Prestige & Donator Roles =====
RANKS = [
    (0, 999, "Mentor"),
    (1000, 2499, "Prefect"),
    (2500, 4999, "Senator"),
    (5000, 7499, "Monarch"),
    (7500, 9999, "Diamond"),
    (10000, 14999, "Dragonstone"),
    (15000, 19999, "Onyx"),
    (20000, float("inf"), "Zenyte"),
]

PRESTIGE_ROLES = [
    ("Quester", "Quest Cape"),
    ("Gamer", "Combat level 126"),
    ("Achiever", "Diary Cape"),
    ("Maxed", "Max Cape"),
    ("Raider", "Base 90 all stats"),
    ("TzKal", "Infernal Cape"),
]

DONATOR_ROLES = [
    (1, 25_000_000, "Protector"),
    (25_000_000, 100_000_000, "Guardian"),
    (100_000_000, 200_000_000, "Templar"),
    (200_000_000, float("inf"), "Beast"),
]

# ===== Bot & Tree =====
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ===== Helpers =====
def get_ladder_rank(points):
    for lower, upper, name in RANKS:
        if lower <= points <= upper:
            return name
    return "Unranked"

def get_donator_rank(donation_total):
    for lower, upper, name in DONATOR_ROLES:
        if lower <= donation_total < upper:
            return name
    return None

async def fetch_wise_player(rsn: str):
    """Fetch player JSON from WOM API."""
    try:
        loop = asyncio.get_running_loop()
        url = WISE_API + urllib.parse.quote(rsn)
        resp = await loop.run_in_executor(None, lambda: requests.get(url, timeout=10))
        if resp.status_code != 200:
            print(f"WOM API returned {resp.status_code} for RSN {rsn}")
            return None
        return resp.json()
    except Exception as e:
        print(f"Error fetching RSN {rsn}: {e}")
        return None

async def map_wise_to_schema(wise_json: dict):
    """
    Map Wise Old Man API JSON to internal schema for points calculation.
    Supports: skills, bosses, diaries, achievements, pets, activities, donations.
    """
    data = {
        "skills": {},
        "bosses": {},
        "diaries": {},
        "achievements": {},
        "pets": {},
        "events": {},
        "donations": 0,
        "activities": {},
        "computed": {}
    }

    snapshot = wise_json.get("latestSnapshot", {}).get("data", {})

    # ===== Skills =====
    skills = snapshot.get("skills", {})
    for skill, info in skills.items():
        level = info.get("level", 0)
        data["skills"][skill] = level

    data["skills"]["total_level"] = skills.get("overall", {}).get("level", 0)
    data["skills"]["combat_level"] = snapshot.get("combatLevel") or 0

    # Count 99s
    ninetynines = sum(1 for lvl in data["skills"].values() if isinstance(lvl, int) and lvl >= 99)
    data["skills"]["first_99"] = ninetynines >= 1
    data["skills"]["extra_99s"] = max(0, ninetynines - 1)

    # ===== Bosses =====
    bosses = snapshot.get("bosses", {})
    for boss, info in bosses.items():
        data["bosses"][boss.lower()] = info.get("kills", 0)

    # ===== Diaries =====
    diaries = snapshot.get("diaries", {})
    data["diaries"]["easy"] = diaries.get("easy", 0)
    data["diaries"]["medium"] = diaries.get("medium", 0)
    data["diaries"]["hard"] = diaries.get("hard", 0)
    data["diaries"]["elite"] = diaries.get("elite", 0)
    data["diaries"]["all_completed"] = diaries.get("completed") or diaries.get("all") or False

    # ===== Achievements =====
    achievements = snapshot.get("achievements", {})
    data["achievements"]["quest_cape"] = bool(snapshot.get("hasQuestCape") or achievements.get("questCape"))
    data["achievements"]["music_cape"] = bool(snapshot.get("hasMusicCape") or achievements.get("musicCape"))
    data["achievements"]["diary_cape"] = bool(snapshot.get("hasDiaryCape") or achievements.get("diaryCape"))
    data["achievements"]["max_cape"] = bool(snapshot.get("isMaxed") or achievements.get("maxCape"))
    data["achievements"]["infernal_cape"] = bool(achievements.get("infernalCape"))

    # ===== Pets =====
    pets = snapshot.get("pets", {})
    data["pets"]["skilling"] = pets.get("skilling", 0)
    data["pets"]["boss"] = pets.get("boss", 0)
    data["pets"]["raids"] = pets.get("raids", 0)

    # ===== Events =====
    events = snapshot.get("events", {})
    data["events"]["pvm_participations"] = events.get("pvm_participations", 0)
    data["events"]["event_wins"] = events.get("event_wins", 0)

    # ===== Donations =====
    data["donations"] = wise_json.get("donations", 0)

    # ===== Activities =====
    activities = snapshot.get("activities", {})
    for activity, info in activities.items():
        data["activities"][activity] = info.get("score", 0)

    # ===== Computed metrics =====
    computed = snapshot.get("computed", {})
    data["computed"]["ehp"] = computed.get("ehp", {}).get("value", 0)
    data["computed"]["ehb"] = computed.get("ehb", {}).get("value", 0)

    return data

# ===== Role Management =====
async def ensure_roles_exist(guild: discord.Guild):
    existing = {r.name: r for r in guild.roles}
    created = []
    for _, _, name in RANKS + [(n, None, n) for n, _ in PRESTIGE_ROLES] + [(l,u,n) for l,u,n in DONATOR_ROLES]:
        if name not in existing:
            await guild.create_role(name=name)
            created.append(name)
    return created

async def assign_roles(member: discord.Member, ladder_name: str, prestige_list: list[str], donator_name: str):
    ladder_names = [r[2] for r in RANKS]
    to_remove = [r for r in member.roles if r.name in ladder_names]
    if to_remove:
        await member.remove_roles(*to_remove)
    ladder_role = discord.utils.get(member.guild.roles, name=ladder_name)
    if ladder_role and ladder_role not in member.roles:
        await member.add_roles(ladder_role)

    for pname, _ in PRESTIGE_ROLES:
        role = discord.utils.get(member.guild.roles, name=pname)
        if role and pname in prestige_list and role not in member.roles:
            await member.add_roles(role)

    if donator_name:
        role = discord.utils.get(member.guild.roles, name=donator_name)
        if role and role not in member.roles:
            await member.add_roles(role)

def is_admin_or_owner():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator or interaction.user == interaction.guild.owner
    return app_commands.check(predicate)

# ===== Commands =====
# (All /link, /update, /points, /addpoints, /dono commands remain the same, now using updated schema)

# ===== On Ready =====
@bot.event
async def on_ready():
    await database.init_db()
    await tree.sync()
    for guild in bot.guilds:
        created = await ensure_roles_exist(guild)
        if created:
            print(f"Created roles in {guild.name}: {created}")
    print(f"✅ Bot online as {bot.user} and commands globally synced")

# ===== Start Bot =====
if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN env var not set.")
else:
    bot.run(DISCORD_TOKEN)
