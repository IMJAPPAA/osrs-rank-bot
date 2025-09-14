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
import database
from pointsystem import calculate_points
import urllib.parse

# ===== Config =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WISE_API = "https://api.wiseoldman.net/v2/players/"

# ===== Ladder Ranks =====
RANKS = [
    (0, "Bronze"),
    (1000, "Iron"),
    (2500, "Rune"),
    (5000, "Dragon"),
    (10000, "Grandmaster"),
    (20000, "Legend"),
]

# ===== Prestige Roles =====
PRESTIGE_ROLES = [
    "Quester", "Musician", "Achiever", "Maxed", "Elite", "126",
    "Barrows/Enforcer", "TzTok", "Pet Hunter"
]

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
            return None
        return resp.json()
    except Exception:
        return None

async def map_wise_to_schema(wise_json: dict):
    data = {
        "bosses": {},
        "diaries": {"easy":0,"medium":0,"hard":0,"elite":0,"all_completed":False},
        "achievements": {"quest_cape":False,"music_cape":False,"diary_cape":False,"max_cape":False},
        "skills": {"first_99":False,"extra_99s":0,"total_level":0},
        "pets": {"skilling":0,"boss":0,"raids":0},
        "events": {"pvm_participations":0,"event_wins":0},
        "donations": 0,
        "first_time_kills": 0
    }

    # Total level
    levels = wise_json.get("levels") or wise_json.get("experience") or {}
    data["skills"]["total_level"] = int(levels.get("overall", {}).get("level", 0) or 0)

    # 99s
    ninetynines = 0
    if isinstance(levels, dict):
        for v in levels.values():
            lvl = v.get("level") if isinstance(v, dict) else 0
            if lvl >= 99:
                ninetynines += 1
    data["skills"]["first_99"] = ninetynines >= 1
    data["skills"]["extra_99s"] = max(0, ninetynines - 1)

    # Bosses
    bosses_source = wise_json.get("bosses") or wise_json.get("bossRecords") or {}
    for key in ["barrows","zulrah","vorkath","gwd","wildy","jad","zuk","cox","tob","toa"]:
        data["bosses"][key] = int(bosses_source.get(key, 0) or 0)

    # Diaries
    diaries = wise_json.get("diaries") or {}
    data["diaries"]["easy"] = int(diaries.get("easy", 0) or 0)
    data["diaries"]["medium"] = int(diaries.get("medium", 0) or 0)
    data["diaries"]["hard"] = int(diaries.get("hard", 0) or 0)
    data["diaries"]["elite"] = int(diaries.get("elite", 0) or 0)
    data["diaries"]["all_completed"] = diaries.get("completed", False)

    # Achievements
    data["achievements"]["quest_cape"] = bool(wise_json.get("hasQuestCape"))
    data["achievements"]["music_cape"] = bool(wise_json.get("hasMusicCape"))
    data["achievements"]["diary_cape"] = bool(wise_json.get("hasDiaryCape"))
    data["achievements"]["max_cape"] = bool(wise_json.get("isMaxed"))

    # Pets
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
    for pname in PRESTIGE_ROLES:
        if pname not in existing:
            role = await guild.create_role(name=pname)
            created.append(role.name)
    return created

async def assign_roles(member: discord.Member, ladder_rank_name: str, prestige_list: list[str]):
    # Ladder rank
    ladder_names = [r[1] for r in RANKS]
    to_remove = [r for r in member.roles if r.name in ladder_names]
    if to_remove:
        await member.remove_roles(*to_remove)
    ladder_role = discord.utils.get(member.guild.roles, name=ladder_rank_name)
    if ladder_role and ladder_role not in member.roles:
        await member.add_roles(ladder_role)

    # Prestige roles
    for prestige_name in prestige_list:
        prestige_role = discord.utils.get(member.guild.roles, name=prestige_name)
        if prestige_role and prestige_role not in member.roles:
            await member.add_roles(prestige_role)

# ===== Commands =====
@tree.command(name="link", description="Link je RSN aan je Discord account")
async def link(interaction: discord.Interaction, rsn: str):
    await database.link_player(str(interaction.user.id), rsn)
    await interaction.response.send_message(
        f"✅ {interaction.user.mention}, je RSN **{rsn}** is gelinkt. Gebruik `/update` om punten te laden."
    )

@tree.command(name="update", description="Update je punten en rollen")
async def update(interaction: discord.Interaction, rsn: str = None):
    discord_id = str(interaction.user.id)
    stored = await database.get_player(discord_id)
    if not stored and not rsn:
        return await interaction.response.send_message("❌ Je moet eerst een RSN linken met `/link <rsn>`.")

    target_rsn = rsn if rsn else stored[0]
    await interaction.response.defer(thinking=True)

    wise_json = await fetch_wise_player(target_rsn)
    if not wise_json:
        return await interaction.followup.send(f"❌ RSN `{target_rsn}` niet gevonden op Wise Old Man.")

    mapped = await map_wise_to_schema(wise_json)
    total_points = calculate_points(mapped)

    if not stored:
        await database.link_player(discord_id, target_rsn)
    await database.update_points(discord_id, total_points)
    ladder_name = get_rank(total_points)

    # Prestige toekennen
    prestige_awards = []
    a = mapped.get("achievements", {})
    d = mapped.get("diaries", {})
    s = mapped.get("skills", {})
    p = mapped.get("pets", {})
    b = mapped.get("bosses", {})

    if a.get("quest_cape"): prestige_awards.append("Quester")
    if a.get("music_cape"): prestige_awards.append("Musician")
    if a.get("diary_cape"): prestige_awards.append("Achiever")
    if a.get("max_cape"): prestige_awards.append("Maxed")
    if d.get("elite", 0) >= 1: prestige_awards.append("Elite")
    if s.get("total_level", 0) >= 2277: prestige_awards.append("126")
    if b.get("barrows", 0) >= 10: prestige_awards.append("Barrows/Enforcer")
    if b.get("jad", 0) >= 1: prestige_awards.append("TzTok")
    total_pets = p.get("skilling",0) + p.get("boss",0) + p.get("raids",0)
    if total_pets >= 10: prestige_awards.append("Pet Hunter")

    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards)

    prestige_text = ', '.join(prestige_awards) if prestige_awards else 'Geen'
    await interaction.followup.send(
        f"✅ {interaction.user.mention} — Points: **{total_points}** • Rank: **{ladder_name}** • Prestige: **{prestige_text}**"
    )

@tree.command(name="points", description="Bekijk je punten en rank")
async def points(interaction: discord.Interaction, member: discord.Member = None):
    if member is None:
        member = interaction.user
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.response.send_message(f"❌ {member.mention} heeft nog geen RSN gelinkt.")
    rsn, pts = stored
    rank = get_rank(pts)
    await interaction.response.send_message(
        f"🏆 {member.mention} | RSN: **{rsn}** | Points: **{pts}** | Rank: **{rank}**"
    )

@tree.command(name="leaderboard", description="Bekijk de top 10 spelers")
async def leaderboard(interaction: discord.Interaction):
    top = await database.get_leaderboard(10)
    if not top:
        return await interaction.response.send_message("❌ Nog geen spelers gevonden.")
    msg = "🏆 **Leaderboard** 🏆\n"
    for i, (rsn, pts) in enumerate(top, start=1):
        msg += f"**{i}.** {rsn} — {pts} points\n"
    await interaction.response.send_message(msg)

# ===== On Ready Event =====
@bot.event
async def on_ready():
    await database.init_db()
    await tree.sync()
    for guild in bot.guilds:
        await ensure_roles_exist(guild)
    print(f"✅ Bot is online als {bot.user}")

# ===== Start Bot =====
if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN is niet gezet.")
else:
    bot.run(DISCORD_TOKEN)
