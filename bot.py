# ===== Dummy audioop module =====
import sys, types
sys.modules['audioop'] = types.ModuleType('audioop')

# ===== Imports =====
import os, asyncio, requests, discord, urllib.parse
from discord.ext import commands
from discord import app_commands
import database
from pointsystem import calculate_points, get_prestige_roles

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
    data = {"bosses": {}, "diaries": {}, "achievements": {}, "skills": {}, "pets": {}, "events": {}, "donations": 0}
    levels = wise_json.get("levels") or wise_json.get("experience") or {}
    data["skills"]["total_level"] = int(levels.get("overall", {}).get("level", 0) or 0)
    data["skills"]["combat_level"] = int(levels.get("combat", {}).get("level", 0) or 0)
    ninetynines = sum(1 for v in levels.values() if isinstance(v, dict) and v.get("level",0)>=99)
    data["skills"]["first_99"] = ninetynines>=1
    data["skills"]["extra_99s"] = max(0, ninetynines-1)

    bosses = wise_json.get("bosses") or wise_json.get("bossRecords") or {}
    for b in bosses:
        data["bosses"][b.lower()] = int(bosses.get(b,0) or 0)

    diaries = wise_json.get("diaries") or {}
    data["diaries"]["easy"] = int(diaries.get("easy",0) or 0)
    data["diaries"]["medium"] = int(diaries.get("medium",0) or 0)
    data["diaries"]["hard"] = int(diaries.get("hard",0) or 0)
    data["diaries"]["elite"] = int(diaries.get("elite",0) or 0)
    data["diaries"]["all_completed"] = diaries.get("completed", False) or diaries.get("all", False)

    achievements = wise_json.get("titles") or wise_json.get("achievements") or {}
    data["achievements"]["quest_cape"] = bool(wise_json.get("hasQuestCape") or achievements.get("questCape"))
    data["achievements"]["music_cape"] = bool(wise_json.get("hasMusicCape") or achievements.get("musicCape"))
    data["achievements"]["diary_cape"] = bool(achievements.get("diaryCape") or wise_json.get("hasDiaryCape"))
    data["achievements"]["max_cape"] = bool(achievements.get("maxCape") or wise_json.get("isMaxed"))
    data["achievements"]["infernal_cape"] = bool(achievements.get("infernalCape"))

    pets = wise_json.get("pets") or {}
    data["pets"]["skilling"] = int(pets.get("skilling",0) or 0)
    data["pets"]["boss"] = int(pets.get("boss",0) or 0)
    data["pets"]["raids"] = int(pets.get("raids",0) or 0)

    # Example events and donations placeholders
    data["events"]["pvm_participations"] = int(wise_json.get("pvm_participations", 0))
    data["events"]["event_wins"] = int(wise_json.get("event_wins", 0))
    data["donations"] = int(wise_json.get("donations", 0))

    return data

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

    donator_names = [r[2] for r in DONATOR_ROLES]
    old_roles = [r for r in member.roles if r.name in donator_names]
    if old_roles:
        await member.remove_roles(*old_roles)
    if donator_name:
        role = discord.utils.get(member.guild.roles, name=donator_name)
        if role and role not in member.roles:
            await member.add_roles(role)

def is_admin_or_owner():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator or interaction.user == interaction.guild.owner
    return app_commands.check(predicate)

# ===== Commands =====

# --- /link ---
@tree.command(name="link", description="Link your OSRS account")
@app_commands.describe(
    rsn="Your RuneScape display name",
    total_level="Optional: Your total level to prefill points",
    combat_level="Optional: Your combat level to prefill points"
)
async def link(interaction: discord.Interaction, rsn: str, total_level: int = None, combat_level: int = None):
    # Implementation from your current /link
    ...

# --- /update ---
@tree.command(name="update", description="Update your points and roles")
async def update(interaction: discord.Interaction, rsn: str = None, donations: int = 0):
    # Full implementation with English messages
    ...

# --- /points ---
@tree.command(name="points", description="Check your points and rank")
async def points(interaction: discord.Interaction, member: discord.Member = None):
    ...

# --- /addpoints ---
@tree.command(name="addpoints", description="Add points to a user (Admin/Owner only)")
@is_admin_or_owner()
async def addpoints(interaction: discord.Interaction, member: discord.Member, points: int, donations: int = 0):
    ...

# --- /dono ---
@tree.command(name="dono", description="Set a user's donator amount and assign rank (Admin/Owner only)")
@is_admin_or_owner()
async def dono(interaction: discord.Interaction, member: discord.Member, amount: int):
    ...

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
