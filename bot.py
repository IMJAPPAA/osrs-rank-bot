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

# ===== Config =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WISE_API = "https://api.wiseoldman.net/v2/players/"

# Ladder ranks & prestige roles
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

# (map_wise_to_schema en role functions behouden zoals in jouw code)

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
        return await interaction.response.send_message("❌ You need to link an RSN first using `/link <rsn>` or provide an RSN in this command.")
    target_rsn = rsn if rsn else stored[0]

    await interaction.response.send_message("🔄 Fetching player data...")

    wise_json = await fetch_wise_player(target_rsn)
    if not wise_json:
        return await interaction.followup.send("❌ Could not fetch player data from Wise Old Man API. Make sure the RSN is correct.")

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

    if a.get("quest_cape"):
        prestige_awards.append("Quester")
    if a.get("music_cape"):
        prestige_awards.append("Musician")
    if a.get("diary_cape"):
        prestige_awards.append("Achiever")
    if a.get("max_cape"):
        prestige_awards.append("Maxed")
    if d.get("elite", 0) >= 1:
        prestige_awards.append("Elite")
    if s.get("total_level", 0) >= 2277:
        prestige_awards.append("126")
    if b.get("barrows", 0) >= 1:
        prestige_awards.append("Barrows/Enforcer")
    if b.get("zulrah", 0) >= 1 or b.get("vorkath", 0) >= 1:
        prestige_awards.append("TzTok")
    total_pets = p.get("skilling",0) + p.get("boss",0) + p.get("raids",0)
    if total_pets >= 30:
        prestige_awards.append("Pet Hunter")

    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards)

    await interaction.followup.send(f"✅ {interaction.user.mention} — Points: **{points}** • Ladder Rank: **{ladder_name}** • Prestige: **{', '.join(prestige_awards) if prestige_awards else 'None'}**")

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

# ===== On Ready Event =====
@bot.event
async def on_ready():
    await tree.sync()
    print(f"Bot is online as {bot.user}")
    await database.init_db()
    for guild in bot.guilds:
        created = await ensure_roles_exist(guild)
        if created:
            print(f"Created roles in {guild.name}: {created}")

# ===== Start Bot =====
if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN env var not set. Set it in Render (or locally) and restart.")
else:
    bot.run(DISCORD_TOKEN)
