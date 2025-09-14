# ===== Dummy audioop module =====
import sys
import types
sys.modules['audioop'] = types.ModuleType('audioop')

# ===== Imports =====
import os
import asyncio
import requests
import discord
from discord.ext import commands
from discord import app_commands
import database  # Zorg dat je deze hebt
from pointsystem import calculate_points  # Zorg dat je deze hebt
import re
import urllib.parse

# ===== Config =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WISE_API = "https://api.wiseoldman.net/v2/players/"

# ===== Ladder ranks & prestige roles =====
RANKS = [
    (0, "Bronze"),
    (1000, "Iron"),
    (2500, "Rune"),
    (5000, "Dragon"),
    (10000, "Grandmaster"),
    (20000, "Legend"),
]

PRESTIGE_ROLES = {
    "Quester": "quest_cape",
    "Musician": "music_cape",
    "Achiever": "diary_cape",
    "Maxed": "max_cape",
    "Elite": "elite_diary",
    "126": "total_level_126",
    "Barrows/Enforcer": "barrows_10",
    "TzTok": "firecape",
    "Pet Hunter": "total_pets_10"
}

# ===== Bot & Slash Command Tree =====
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ===== Helper Functions =====
def get_rank(points):
    rank = "Unranked"
    for threshold, name in RANKS:
        if points >= threshold:
            rank = name
    return rank

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
    # Map JSON naar standaard schema
    data = {
        "bosses": {},
        "diaries": {"easy":0,"medium":0,"hard":0,"elite":0,"all_completed":False},
        "achievements": {"quest_cape":False, "music_cape":False, "diary_cape":False, "max_cape":False},
        "skills": {"first_99":False, "extra_99s":0, "total_level":0},
        "pets": {"skilling":0, "boss":0, "raids":0},
        "events": {"pvm_participations":0, "event_wins":0},
        "donations": 0,
        "first_time_kills": 0
    }
    levels = wise_json.get("levels") or wise_json.get("experience") or {}
    overall_level = int(levels.get("overall", {}).get("level", 0) or 0)
    data["skills"]["total_level"] = overall_level

    ninetynines = 0
    if isinstance(levels, dict):
        for v in levels.values():
            lvl = v.get("level") if isinstance(v, dict) else 0
            if lvl >= 99:
                ninetynines += 1
    data["skills"]["first_99"] = ninetynines >= 1
    data["skills"]["extra_99s"] = max(0, ninetynines - 1)

    bosses_source = wise_json.get("bosses") or wise_json.get("bossRecords") or {}
    for key in ["barrows", "zulrah", "vorkath", "gwd", "wildy", "jad", "zuk", "cox", "tob", "toa"]:
        data["bosses"][key] = int(bosses_source.get(key, 0) or 0)

    diaries = wise_json.get("diaries") or {}
    data["diaries"]["easy"] = int(diaries.get("easy", 0) or 0)
    data["diaries"]["medium"] = int(diaries.get("medium", 0) or 0)
    data["diaries"]["hard"] = int(diaries.get("hard", 0) or 0)
    data["diaries"]["elite"] = int(diaries.get("elite", 0) or 0)
    data["diaries"]["all_completed"] = diaries.get("completed", False) or diaries.get("all", False)

    achievements = wise_json.get("titles") or wise_json.get("achievements") or {}
    data["achievements"]["quest_cape"] = bool(wise_json.get("hasQuestCape") or achievements.get("questCape"))
    data["achievements"]["music_cape"] = bool(wise_json.get("hasMusicCape") or achievements.get("musicCape"))
    data["achievements"]["diary_cape"] = bool(achievements.get("diaryCape") or wise_json.get("hasDiaryCape"))
    data["achievements"]["max_cape"] = bool(achievements.get("maxCape") or wise_json.get("isMaxed"))

    pets = wise_json.get("pets") or {}
    data["pets"]["skilling"] = int(pets.get("skilling", 0) or 0)
    data["pets"]["boss"] = int(pets.get("boss", 0) or 0)
    data["pets"]["raids"] = int(pets.get("raids", 0) or 0)

    return data

async def ensure_roles_exist(guild: discord.Guild):
    existing = {r.name: r for r in guild.roles}
    created = []
    for _, name in RANKS:
        if name not in existing:
            role = await guild.create_role(name=name)
            created.append(role.name)
    for pname in PRESTIGE_ROLES.keys():
        if pname not in existing:
            role = await guild.create_role(name=pname)
            created.append(role.name)
    return created

async def assign_roles(member: discord.Member, ladder_rank_name: str, prestige_list: list[str]):
    # ---- Ladder roles ----
    ladder_names = [r[1] for r in RANKS]
    to_remove = [r for r in member.roles if r.name in ladder_names]
    if to_remove:
        await member.remove_roles(*to_remove)
    ladder_role = discord.utils.get(member.guild.roles, name=ladder_rank_name)
    if ladder_role and ladder_role not in member.roles:
        await member.add_roles(ladder_role)

    # ---- Prestige roles ----
    for prestige_name in prestige_list:
        role = discord.utils.get(member.guild.roles, name=prestige_name)
        if role and role not in member.roles:
            await member.add_roles(role)

# ===== Admin/Owner check =====
def is_admin_or_owner():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator or interaction.user == interaction.guild.owner
    return app_commands.check(predicate)

# ===== Slash Commands =====
@tree.command(name="link", description="Link your OSRS account")
async def link(interaction: discord.Interaction, rsn: str):
    await database.link_player(str(interaction.user.id), rsn)
    await interaction.response.send_message(f"✅ {interaction.user.mention}, your RSN **{rsn}** has been linked. Use `/update` to fetch your points.")

@tree.command(name="update", description="Update your points and roles")
async def update(interaction: discord.Interaction, rsn: str = None):
    discord_id = str(interaction.user.id)
    stored = await database.get_player(discord_id)
    if not stored and not rsn:
        return await interaction.response.send_message("❌ Je moet eerst een RSN linken met `/link <rsn>` of een RSN opgeven.")

    target_rsn = rsn if rsn else stored[0]
    await interaction.response.defer(thinking=True)

    wise_json = await fetch_wise_player(target_rsn)
    if not wise_json:
        return await interaction.followup.send(f"❌ Could not fetch player data from Wise Old Man. Check RSN `{target_rsn}` of probeer later opnieuw.")

    mapped = await map_wise_to_schema(wise_json)
    base_points = calculate_points(mapped)
    manual_points = 0 if not stored else max(0, stored[1] - base_points)
    total_points = base_points + manual_points

    if not stored:
        await database.link_player(discord_id, target_rsn)
    await database.update_points(discord_id, total_points)

    ladder_name = get_rank(total_points)
    prestige_awards = []

    # Prestige mapping
    if mapped["achievements"]["quest_cape"]: prestige_awards.append("Quester")
    if mapped["achievements"]["music_cape"]: prestige_awards.append("Musician")
    if mapped["achievements"]["diary_cape"]: prestige_awards.append("Achiever")
    if mapped["achievements"]["max_cape"]: prestige_awards.append("Maxed")
    if mapped["diaries"]["elite"] >= 1: prestige_awards.append("Elite")
    if mapped["skills"]["total_level"] >= 126: prestige_awards.append("126")
    if mapped["bosses"]["barrows"] >= 10: prestige_awards.append("Barrows/Enforcer")
    if mapped["bosses"]["zulrah"] >= 1: prestige_awards.append("TzTok")
    total_pets = mapped["pets"]["skilling"] + mapped["pets"]["boss"] + mapped["pets"]["raids"]
    if total_pets >= 10: prestige_awards.append("Pet Hunter")

    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards)

    prestige_text = ', '.join(prestige_awards) if prestige_awards else 'None'
    await interaction.followup.send(f"✅ {interaction.user.mention} — Points: **{total_points}** • Ladder Rank: **{ladder_name}** • Prestige: **{prestige_text}")

# ===== /points command =====
@tree.command(name="points", description="Check your points and rank")
async def points(interaction: discord.Interaction, member: discord.Member = None):
    if member is None:
        member = interaction.user
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.response.send_message(f"❌ {member.mention} has not linked an RSN yet.")
    rsn, pts = stored
    rank = get_rank(pts)
    await interaction.response.send_message(f"🏆 {member.mention} | RSN: **{rsn}** | Points: **{pts}** | Rank: **{rank}**")

# ===== /requestpoint =====
@tree.command(name="requestpoint", description="Request points (must be approved by admin)")
async def requestpoint(interaction: discord.Interaction, rsn: str, amount: int):
    await interaction.response.defer(thinking=True)
    if amount <= 0:
        return await interaction.followup.send("❌ Points must be greater than 0.")
    await database.add_point_request(str(interaction.user.id), rsn, amount)
    await interaction.followup.send(f"📨 {interaction.user.mention}, your request for **{amount} points** has been submitted for admin approval.")

# ===== /approve =====
@tree.command(name="approve", description="Approve a point request (Admin/Owner only)")
@is_admin_or_owner()
async def approve(interaction: discord.Interaction, request_id: int):
    pending = await database.get_pending_requests()
    req = next((r for r in pending if r['id'] == request_id), None)
    if not req:
        return await interaction.response.send_message(f"❌ Request ID {request_id} not found.")
    stored = await database.get_player(req['discord_id'])
    current_points = stored[1] if stored else 0
    new_points = current_points + req['points']
    await database.update_points(req['discord_id'], new_points)
    await database.update_request_status(request_id, "approved")
    await interaction.response.send_message(f"✅ Request ID {request_id} approved and points added.")

# ===== /addpoints =====
@tree.command(name="addpoints", description="Add points to a user (Admin/Owner only)")
@is_admin_or_owner()
async def addpoints(interaction: discord.Interaction, member: discord.Member, points: int):
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.response.send_message(f"❌ {member.mention} has not linked an RSN yet.")
    rsn, current_points = stored
    new_points = current_points + points
    await database.update_points(str(member.id), new_points)
    await interaction.response.send_message(f"✅ {points} points added to {member.mention}. Total points: {new_points}")

# ===== On ready =====
@bot.event
async def on_ready():
    await database.init_db()
    await tree.sync()
    for guild in bot.guilds:
        created = await ensure_roles_exist(guild)
        if created:
            print(f"Created roles in {guild.name}: {created}")
    print(f"✅ Bot online as {bot.user} and commands synced globally")

# ===== Start Bot =====
if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN env var not set.")
else:
    bot.run(DISCORD_TOKEN)
