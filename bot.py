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
import database  # zorg dat je deze hebt
from pointsystem import calculate_points  # zorg dat je deze hebt
import re
import urllib.parse

# ===== Config =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WISE_API = "https://api.wiseoldman.net/v2/players/"

# ===== Ladder & prestige roles =====
RANKS = [
    (0, "Bronze"),
    (1000, "Iron"),
    (2500, "Rune"),
    (5000, "Dragon"),
    (10000, "Grandmaster"),
    (20000, "Legend"),
]

PRESTIGE_ROLES = [
    "Barrows/Enforcer", "Skillcape", "TzTok", "Quester", "Musician", "Elite",
    "126", "Achiever", "Champion", "Quiver", "TzKal", "Cape Haver", "Master",
    "Braindead", "Leaguer", "Maxed", "Clogger", "Kitted", "Pet Hunter", "Last Event Winner"
]

# ===== Bot & Tree =====
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ===== Helpers =====
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
    data = {
        "bosses": {}, "diaries": {"easy":0,"medium":0,"hard":0,"elite":0,"all_completed":False},
        "achievements": {"quest_cape":False,"music_cape":False,"diary_cape":False,"max_cape":False},
        "skills": {"first_99":False,"extra_99s":0,"total_level":0}, "pets": {"skilling":0,"boss":0,"raids":0}
    }
    levels = wise_json.get("levels") or wise_json.get("experience") or {}
    overall_level = int(levels.get("overall", {}).get("level", 0) or 0)
    data["skills"]["total_level"] = overall_level
    ninetynines = sum(1 for v in levels.values() if isinstance(v, dict) and v.get("level",0) >= 99)
    data["skills"]["first_99"] = ninetynines >= 1
    data["skills"]["extra_99s"] = max(0, ninetynines -1)
    bosses_source = wise_json.get("bosses") or wise_json.get("bossRecords") or {}
    for key in ["barrows","zulrah","vorkath","gwd","wildy","jad","zuk","cox","tob","toa"]:
        data["bosses"][key] = int(bosses_source.get(key,0) or 0)
    diaries = wise_json.get("diaries") or {}
    for lvl in ["easy","medium","hard","elite"]:
        data["diaries"][lvl] = int(diaries.get(lvl,0) or 0)
    data["diaries"]["all_completed"] = diaries.get("completed", False) or diaries.get("all", False)
    achievements = wise_json.get("titles") or wise_json.get("achievements") or {}
    data["achievements"]["quest_cape"] = bool(wise_json.get("hasQuestCape") or achievements.get("questCape"))
    data["achievements"]["music_cape"] = bool(wise_json.get("hasMusicCape") or achievements.get("musicCape"))
    data["achievements"]["diary_cape"] = bool(achievements.get("diaryCape") or wise_json.get("hasDiaryCape"))
    data["achievements"]["max_cape"] = bool(achievements.get("maxCape") or wise_json.get("isMaxed"))
    pets = wise_json.get("pets") or {}
    for k in ["skilling","boss","raids"]:
        data["pets"][k] = int(pets.get(k,0) or 0)
    return data

async def ensure_roles_exist(guild: discord.Guild):
    existing = {r.name:r for r in guild.roles}
    created = []
    for _, name in RANKS + [(0,r) for r in PRESTIGE_ROLES]:
        if name not in existing:
            role = await guild.create_role(name=name)
            created.append(role.name)
    return created

async def assign_roles(member: discord.Member, ladder_rank_name: str, prestige_list):
    ladder_names = [r[1] for r in RANKS]
    to_remove = [r for r in member.roles if r.name in ladder_names]
    if to_remove:
        await member.remove_roles(*to_remove)
    guild_role = discord.utils.get(member.guild.roles, name=ladder_rank_name)
    if guild_role:
        await member.add_roles(guild_role)
    for p in prestige_list:
        role = discord.utils.get(member.guild.roles, name=p)
        if role and role not in member.roles:
            await member.add_roles(role)
    clean_name = re.sub(r'^:[^:]+:\s*','',member.display_name)
    try: await member.edit(nick=clean_name)
    except: pass

# ===== Slash Commands =====
@tree.command(name="link", description="Link your OSRS account")
async def link(interaction: discord.Interaction, rsn: str):
    await interaction.response.defer(thinking=True)
    await database.link_player(str(interaction.user.id), rsn)
    await interaction.followup.send(f"✅ {interaction.user.mention}, your RSN **{rsn}** has been linked. Use `/update` to fetch your points.")

@tree.command(name="update", description="Update your points and roles")
async def update(interaction: discord.Interaction, rsn: str = None):
    await interaction.response.defer(thinking=True)
    discord_id = str(interaction.user.id)
    stored = await database.get_player(discord_id)
    if not stored and not rsn:
        return await interaction.followup.send("❌ You must link your RSN first with `/link <rsn>` or provide RSN here.")
    target_rsn = rsn if rsn else stored[0]
    wise_json = await fetch_wise_player(target_rsn)
    if not wise_json:
        return await interaction.followup.send(f"❌ Could not fetch player data from Wise Old Man. Check RSN `{target_rsn}`.")
    mapped = await map_wise_to_schema(wise_json)
    base_points = calculate_points(mapped)
    manual_points = 0 if not stored else max(0, stored[1] - base_points)
    total_points = base_points + manual_points
    if not stored:
        await database.link_player(discord_id, target_rsn)
    await database.update_points(discord_id, total_points)
    ladder_name = get_rank(total_points)
    prestige_awards = []
    a = mapped.get("achievements",{})
    d = mapped.get("diaries",{})
    s = mapped.get("skills",{})
    p = mapped.get("pets",{})
    b = mapped.get("bosses",{})
    if a.get("quest_cape"): prestige_awards.append("Quester")
    if a.get("music_cape"): prestige_awards.append("Musician")
    if a.get("diary_cape"): prestige_awards.append("Achiever")
    if a.get("max_cape"): prestige_awards.append("Maxed")
    if d.get("elite",0) >=1: prestige_awards.append("Elite")
    if s.get("total_level",0) >=2277: prestige_awards.append("126")
    if b.get("barrows",0) >=1: prestige_awards.append("Barrows/Enforcer")
    if b.get("zulrah",0)>=1 or b.get("vorkath",0)>=1: prestige_awards.append("TzTok")
    total_pets = p.get("skilling",0)+p.get("boss",0)+p.get("raids",0)
    if total_pets>=30: prestige_awards.append("Pet Hunter")
    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards)
    prestige_text = ', '.join(prestige_awards) if prestige_awards else 'None'
    await interaction.followup.send(f"✅ {interaction.user.mention} — Points: **{total_points}** • Ladder Rank: **{ladder_name}** • Prestige: **{prestige_text}**")

@tree.command(name="points", description="Check your points and rank")
async def points(interaction: discord.Interaction, member: discord.Member = None):
    if member is None: member = interaction.user
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.response.send_message(f"❌ {member.mention} has not linked an RSN yet.")
    rsn, pts = stored
    rank = get_rank(pts)
    await interaction.response.send_message(f"🏆 {member.mention} | RSN: **{rsn}** | Points: **{pts}** | Rank: **{rank}**")

@tree.command(name="requestpoint", description="Request points for your account")
async def requestpoint(interaction: discord.Interaction, rsn: str, amount: int):
    await interaction.response.defer(thinking=True)
    if amount <= 0:
        return await interaction.followup.send("❌ Points must be greater than 0.")
    discord_id = str(interaction.user.id)
    await database.add_point_request(discord_id, rsn, amount)
    await interaction.followup.send(f"📨 {interaction.user.mention}, your request for **{amount} points** for RSN `{rsn}` has been submitted. An admin will review it.")

# ===== On Ready Event =====
@bot.event
async def on_ready():
    await database.init_db()
    await tree.sync()
    for guild in bot.guilds:
        created = await ensure_roles_exist(guild)
        if created: print(f"Created roles in {guild.name}: {created}")
    print(f"✅ Bot online as {bot.user}, commands synced.")

# ===== Run Bot =====
if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN env var not set.")
else:
    bot.run(DISCORD_TOKEN)
