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
import re  # Voor het schoonmaken van nicknames

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

PRESTIGE_ROLES = [
    "Barrows/Enforcer", "Skillcape", "TzTok", "Quester", "Musician", "Elite",
    "126", "Achiever", "Champion", "Quiver", "TzKal", "Cape Haver", "Master",
    "Braindead", "Leaguer", "Maxed", "Clogger", "Kitted", "Pet Hunter", "Last Event Winner"
]

# ===== Emoji mapping (wordt niet gebruikt voor nicknames) =====
RANK_EMOJI = {
    "Bronze": ":Bronze:",
    "Iron": ":Iron:",
    "Rune": ":Rune:",
    "Dragon": ":Dragon:",
    "Grandmaster": ":Dragonhunter:",
    "Legend": ":Zaryte:",
    "Barrows/Enforcer": ":Barrows:",
    "Skillcape": ":Skillcape:",
    "TzTok": ":Firecape:",
    "Quester": ":Quester:",
    "Musician": ":Musician:",
    "Elite": ":Elite:",
    "126": ":scim:",
    "Achiever": ":Achiever:",
    "Champion": ":first_place:",
    "Quiver": ":Quiver:",
    "TzKal": ":Infernal:",
    "Cape Haver": ":CapeHaver:",
    "Master": ":Bloodtorva:",
    "Braindead": ":Braindead:",
    "Leaguer": ":Leaguer:",
    "Maxed": ":Max:",
    "Clogger": ":Clogger:",
    "Kitted": ":Ancestral:",
    "Pet Hunter": ":Kraken:",
    "Last Event Winner": ":GP:"
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
        resp = await loop.run_in_executor(None, lambda: requests.get(WISE_API + rsn, timeout=10))
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None

async def map_wise_to_schema(wise_json: dict):
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
    data["skills"]["total_level"] = int(levels.get("overall", {}).get("level", 0) or 0)

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
        value = bosses_source.get(key, 0)
        data["bosses"][key] = int(value or 0)

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
    for pname in PRESTIGE_ROLES:
        if pname not in existing:
            role = await guild.create_role(name=pname)
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
    
    # ==== Clean nickname: remove any ladder emoji ====
    clean_name = re.sub(r'^:[^:]+:\s*', '', member.display_name)
    try:
        await member.edit(nick=clean_name)
    except:
        pass

# ===== Slash Commands =====
@tree.command(name="link", description="Link your OSRS account")
async def link(interaction: discord.Interaction, rsn: str):
    await database.link_player(str(interaction.user.id), rsn)
    await interaction.response.send_message(f"✅ {interaction.user.mention}, your RSN **{rsn}** has been linked. Use `/update` to fetch your points.")

@tree.command(name="grantpoints", description="Add points to a user (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def grantpoints(interaction: discord.Interaction, member: discord.Member, points: int):
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.response.send_message(f"❌ {member.mention} has not linked an RSN yet.")
    rsn, current_points = stored
    new_points = current_points + points
    await database.update_points(str(member.id), new_points)
    await interaction.response.send_message(f"✅ {points} points added to {member.mention}. Total points: {new_points}")

@tree.command(name="update", description="Update your points and roles")
async def update(interaction: discord.Interaction, rsn: str = None):
    discord_id = str(interaction.user.id)
    stored = await database.get_player(discord_id)
    if not stored and not rsn:
        return await interaction.response.send_message(
            "❌ You need to link an RSN first using `/link <rsn>` or provide an RSN in this command."
        )
    target_rsn = rsn if rsn else stored[0]
    await interaction.response.send_message("🔄 Fetching player data...")
    wise_json = await fetch_wise_player(target_rsn)
    if not wise_json:
        return await interaction.followup.send(
            "❌ Could not fetch player data from Wise Old Man API. Make sure the RSN is correct."
        )
    mapped = await map_wise_to_schema(wise_json)
    points = calculate_points(mapped)
    if not stored:
        await database.link_player(discord_id, target_rsn)
    await database.update_points(discord_id, points)
    ladder_name = get_rank(points)

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
    if b.get("barrows", 0) >= 1: prestige_awards.append("Barrows/Enforcer")
    if b.get("zulrah", 0) >= 1 or b.get("vorkath", 0) >= 1: prestige_awards.append("TzTok")
    total_pets = p.get("skilling",0) + p.get("boss",0) + p.get("raids",0)
    if total_pets >= 30: prestige_awards.append("Pet Hunter")

    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards)

    await interaction.followup.send(
        f"✅ {interaction.user.mention} — Points: **{points}** • Ladder Rank: **{ladder_name}** • Prestige: **{', '.join(prestige_awards) if prestige_awards else 'None'}**"
    )

@tree.command(name="points", description="Check your points and rank")
async def points(interaction: discord.Interaction, member: discord.Member = None):
    if member is None:
        member = interaction.user
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.response.send_message(f"❌ {member.mention} has not linked an RSN yet.")
    rsn, pts = stored
    rank = get_rank(pts)
    await interaction.response.send_message(
        f"🏆 {member.mention} | RSN: **{rsn}** | Points: **{pts}** | Rank: **{rank}**"
    )

# ===== On Ready Event =====
@bot.event
async def on_ready():
    await database.init_db()

    for guild in bot.guilds:
        # Haal alle commands op die in deze guild geregistreerd zijn
        existing_commands = await tree.fetch_commands(guild=guild)

        # Verwijder oude /addpoints command
        for cmd in existing_commands:
            if cmd.name == "addpoints":
                await tree.delete_command(cmd.id, guild=guild)
                print(f"Deleted old command {cmd.name} in {guild.name}")

        # Sync nieuwe commands
        await tree.sync(guild=guild)
        created = await ensure_roles_exist(guild)
        if created:
            print(f"Created roles in {guild.name}: {created}")

    print(f"✅ Bot is online as {bot.user} and commands are synced")


# ===== Start Bot =====
if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN env var not set. Set it in Render (or locally) en restart.")
else:
    bot.run(DISCORD_TOKEN)
