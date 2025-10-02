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

    # Skills
    skills = snapshot.get("skills", {})
    for skill, info in skills.items():
        level = info.get("level", 0)
        data["skills"][skill] = level
    data["skills"]["total_level"] = skills.get("overall", {}).get("level", 0)
    data["skills"]["combat_level"] = snapshot.get("combatLevel") or 0
    ninetynines = sum(1 for lvl in data["skills"].values() if isinstance(lvl, int) and lvl >= 99)
    data["skills"]["first_99"] = ninetynines >= 1
    data["skills"]["extra_99s"] = max(0, ninetynines - 1)

    # Bosses
    bosses = snapshot.get("bosses", {})
    for boss, info in bosses.items():
        data["bosses"][boss.lower()] = info.get("kills", 0)

    # Diaries
    diaries = snapshot.get("diaries", {})
    data["diaries"]["easy"] = diaries.get("easy", 0)
    data["diaries"]["medium"] = diaries.get("medium", 0)
    data["diaries"]["hard"] = diaries.get("hard", 0)
    data["diaries"]["elite"] = diaries.get("elite", 0)
    data["diaries"]["all_completed"] = diaries.get("completed") or diaries.get("all") or False

    # Achievements
    achievements = snapshot.get("achievements", {})
    data["achievements"]["quest_cape"] = bool(snapshot.get("hasQuestCape") or achievements.get("questCape"))
    data["achievements"]["music_cape"] = bool(snapshot.get("hasMusicCape") or achievements.get("musicCape"))
    data["achievements"]["diary_cape"] = bool(snapshot.get("hasDiaryCape") or achievements.get("diaryCape"))
    data["achievements"]["max_cape"] = bool(snapshot.get("isMaxed") or achievements.get("maxCape"))
    data["achievements"]["infernal_cape"] = bool(achievements.get("infernalCape"))

    # Pets
    pets = snapshot.get("pets", {})
    data["pets"]["skilling"] = pets.get("skilling", 0)
    data["pets"]["boss"] = pets.get("boss", 0)
    data["pets"]["raids"] = pets.get("raids", 0)

    # Computed metrics (EHP/EHB)
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
@tree.command(name="link", description="Link your RSN")
async def link(interaction: discord.Interaction, rsn: str):
    await interaction.response.defer(thinking=True)
    wise_json = await fetch_wise_player(rsn)
    if not wise_json:
        return await interaction.followup.send(f"❌ Could not fetch data for RSN `{rsn}`.")

    mapped = await map_wise_to_schema(wise_json)
    # Save boss KC at link moment
    boss_kc_at_link = mapped.get("bosses", {}).copy()

    discord_id = str(interaction.user.id)
    db_player = await database.get_player(discord_id)
    discord_points = db_player[1] if db_player else 0
    donations = db_player[2] if db_player else 0

    wom_points = calculate_points(mapped, boss_kc_at_link)
    total_points = wom_points + discord_points

    await database.link_player(discord_id, rsn, json.dumps(boss_kc_at_link))
    await database.update_points(discord_id, total_points, donations)

    ladder_name = get_ladder_rank(total_points)

    # Prestige
    prestige_awards = []
    a = mapped.get("achievements", {})
    s = mapped.get("skills", {})
    if a.get("quest_cape"): prestige_awards.append("Quester")
    if s.get("combat_level", 0) >= 126: prestige_awards.append("Gamer")
    if a.get("diary_cape"): prestige_awards.append("Achiever")
    if a.get("max_cape"): prestige_awards.append("Maxed")
    if all(level >= 90 for k, level in s.items() if k not in ["total_level","combat_level"]): prestige_awards.append("Raider")
    if a.get("infernal_cape"): prestige_awards.append("TzKal")

    donator_name = get_donator_rank(donations)
    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards, donator_name)

    await interaction.followup.send(
        f"✅ {interaction.user.mention} linked RSN **{rsn}**.\n"
        f"Points: **{total_points}** • Rank: **{ladder_name}** • "
        f"Prestige: {', '.join(prestige_awards) if prestige_awards else 'None'} • "
        f"Donator: {donator_name if donator_name else 'None'}"
    )

# ===== update command with KC delta calculation =====
@tree.command(name="update", description="Update your points")
async def update(interaction: discord.Interaction):
    discord_id = str(interaction.user.id)
    player = await database.get_player(discord_id)
    if not player:
        return await interaction.response.send_message("❌ You have not linked your RSN yet.")

    rsn, discord_points, donations, boss_kc_json = player
    boss_kc_at_link = json.loads(boss_kc_json or "{}")

    wise_json = await fetch_wise_player(rsn)
    if not wise_json:
        return await interaction.response.send_message(f"❌ Could not fetch data for RSN `{rsn}`.")

    mapped = await map_wise_to_schema(wise_json)
    wom_points = calculate_points(mapped, boss_kc_at_link)

    total_points = wom_points + discord_points
    await database.update_points(discord_id, total_points, donations)

    ladder_name = get_ladder_rank(total_points)

    # Prestige
    prestige_awards = []
    a = mapped.get("achievements", {})
    s = mapped.get("skills", {})
    if a.get("quest_cape"): prestige_awards.append("Quester")
    if s.get("combat_level", 0) >= 126: prestige_awards.append("Gamer")
    if a.get("diary_cape"): prestige_awards.append("Achiever")
    if a.get("max_cape"): prestige_awards.append("Maxed")
    if all(level >= 90 for k, level in s.items() if k not in ["total_level","combat_level"]): prestige_awards.append("Raider")
    if a.get("infernal_cape"): prestige_awards.append("TzKal")

    donator_name = get_donator_rank(donations)
    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards, donator_name)

    await interaction.response.send_message(
        f"✅ Updated points: **{total_points}**, Rank: **{ladder_name}**, Donations: **{donations}**"
    )

# ===== Start Bot =====
@bot.event
async def on_ready():
    await database.init_db()
    await tree.sync()
    for guild in bot.guilds:
        created = await ensure_roles_exist(guild)
        if created:
            print(f"Created roles in {guild.name}: {created}")
    print(f"✅ Bot online as {bot.user} and commands globally synced")

if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN env var not set.")
else:
    bot.run(DISCORD_TOKEN)
