# ===== Dummy audioop module =====
import sys, types
sys.modules['audioop'] = types.ModuleType('audioop')

# ===== Imports =====
import os, asyncio, requests, discord, urllib.parse
from discord.ext import commands
from discord import app_commands
import database
from pointsystem import calculate_points

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
    (1, 25_000_000, "Protector"),  # aangepast: start bij 1
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
    data = {"bosses": {}, "diaries": {}, "achievements": {}, "skills": {}, "pets": {}}
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
    # Ladder
    ladder_names = [r[2] for r in RANKS]
    to_remove = [r for r in member.roles if r.name in ladder_names]
    if to_remove:
        await member.remove_roles(*to_remove)
    ladder_role = discord.utils.get(member.guild.roles, name=ladder_name)
    if ladder_role and ladder_role not in member.roles:
        await member.add_roles(ladder_role)

    # Prestige
    for pname, _ in PRESTIGE_ROLES:
        role = discord.utils.get(member.guild.roles, name=pname)
        if role and pname in prestige_list and role not in member.roles:
            await member.add_roles(role)

    # Donator
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
@tree.command(name="link", description="Link your OSRS account")
async def link(interaction: discord.Interaction, rsn: str):
    await database.link_player(str(interaction.user.id), rsn)
    await interaction.response.send_message(f"✅ {interaction.user.mention}, RSN **{rsn}** linked. Use `/update`.")

@tree.command(name="update", description="Update points and roles")
async def update(interaction: discord.Interaction, rsn: str = None, donations: int = 0):
    discord_id = str(interaction.user.id)
    stored = await database.get_player(discord_id)
    if not stored and not rsn:
        return await interaction.response.send_message("❌ Link first with `/link <rsn>`.")
    target_rsn = rsn if rsn else stored[0]
    await interaction.response.defer(thinking=True)

    wise_json = await fetch_wise_player(target_rsn)
    if not wise_json:
        return await interaction.followup.send(f"❌ Could not fetch data for RSN `{target_rsn}`.")

    mapped = await map_wise_to_schema(wise_json)
    base_points = calculate_points(mapped)
    manual_points = 0 if not stored else max(0, stored[1]-base_points)
    total_points = base_points + manual_points

    if not stored:
        await database.link_player(discord_id, target_rsn)
    await database.update_points(discord_id, total_points, donations)

    ladder_name = get_ladder_rank(total_points)

    prestige_awards = []
    a = mapped.get("achievements", {})
    s = mapped.get("skills", {})
    if a.get("quest_cape"): prestige_awards.append("Quester")
    if s.get("combat_level",0)>=126: prestige_awards.append("Gamer")
    if a.get("diary_cape"): prestige_awards.append("Achiever")
    if a.get("max_cape"): prestige_awards.append("Maxed")
    if all(level>=90 for k, level in s.items() if k not in ["total_level","combat_level"]): prestige_awards.append("Raider")
    if a.get("infernal_cape"): prestige_awards.append("TzKal")

    donator_name = get_donator_rank(donations)

    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards, donator_name)

    await interaction.followup.send(
        f"✅ {interaction.user.mention} — Points: **{total_points}** • Rank: **{ladder_name}** • "
        f"Prestige: {', '.join(prestige_awards) if prestige_awards else 'None'} • "
        f"Donator: {donator_name if donator_name else 'None'}"
    )

@tree.command(name="points", description="Check points and rank")
async def points(interaction: discord.Interaction, member: discord.Member = None):
    if not member:
        member = interaction.user
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.response.send_message(f"❌ {member.mention} has not linked RSN.")
    rsn, pts, donations = stored
    ladder_name = get_ladder_rank(pts)
    await interaction.response.send_message(f"🏆 {member.mention} | RSN: **{rsn}** | Points: **{pts}** | Rank: **{ladder_name}** | Donations: **{donations}**")

@tree.command(name="addpoints", description="Add points to a user (Admin/Owner only)")
@is_admin_or_owner()
async def addpoints(interaction: discord.Interaction, member: discord.Member, points: int, donations: int = 0):
    await interaction.response.defer(thinking=True)
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.followup.send(f"❌ {member.mention} has not linked RSN.")
    rsn, current_points, current_donations = stored
    new_points = current_points + points
    new_donations = donations if donations else current_donations
    await database.update_points(str(member.id), new_points, new_donations)

    wise_json = await fetch_wise_player(rsn)
    mapped = await map_wise_to_schema(wise_json) if wise_json else {}
    ladder_name = get_ladder_rank(new_points)

    prestige_awards = []
    a = mapped.get("achievements", {})
    s = mapped.get("skills", {})
    if a.get("quest_cape"): prestige_awards.append("Quester")
    if s.get("combat_level",0)>=126: prestige_awards.append("Gamer")
    if a.get("diary_cape"): prestige_awards.append("Achiever")
    if a.get("max_cape"): prestige_awards.append("Maxed")
    if all(level>=90 for k, level in s.items() if k not in ["total_level","combat_level"]): prestige_awards.append("Raider")
    if a.get("infernal_cape"): prestige_awards.append("TzKal")

    donator_name = get_donator_rank(new_donations)

    await ensure_roles_exist(member.guild)
    await assign_roles(member, ladder_name, prestige_awards, donator_name)

    await interaction.followup.send(
        f"✅ {points} points added to {member.mention}. Total points: {new_points} • "
        f"Donator: {donator_name if donator_name else 'None'}"
    )

@tree.command(name="dono", description="Set a user's donator amount and assign rank (Admin/Owner only)")
@is_admin_or_owner()
async def dono(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.defer(thinking=True)
    donator_name = get_donator_rank(amount)
    if not donator_name:
        return await interaction.followup.send(f"❌ Could not determine donator rank for amount {amount}")

    await database.update_points(str(member.id), donations=amount)

    donator_names = [r[2] for r in DONATOR_ROLES]
    old_roles = [r for r in member.roles if r.name in donator_names]
    if old_roles:
        await member.remove_roles(*old_roles)

    role = discord.utils.get(member.guild.roles, name=donator_name)
    if role and role not in member.roles:
        await member.add_roles(role)

    await interaction.followup.send(f"✅ {member.mention} is now **{donator_name}** (Donated: {amount:,})")

# ===== On Ready =====
@bot.event
async def on_ready():
    await database.init_db()
    await tree.sync()
    for guild in bot.guilds:
        created = await ensure_roles_exist(guild)
        if created:
            print(f"Created roles in {guild.name}: {created}")
    print(f"✅ Bot online als {bot.user} en commands globally gesynced")

# ===== Start Bot =====
if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN env var not set.")
else:
    bot.run(DISCORD_TOKEN)
