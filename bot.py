import os

# Dummy audioop module om crash te voorkomen op Python 3.13+
import sys
import types
sys.modules['audioop'] = types.ModuleType('audioop')

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import requests
import database  # zorg dat je deze hebt
from pointsystem import calculate_points  # zorg dat je deze hebt

# Maak bot en app_commands tree
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
tree = bot.tree

# ===== Slash Commands =====

@tree.command(name="link", description="Link your OSRS account")
async def link(interaction: discord.Interaction, rsn: str):
    # Hier komt jouw code om de account te linken
    await interaction.response.send_message(f"RSN {rsn} linked!")

@tree.command(name="update", description="Update your points and stats")
async def update(interaction: discord.Interaction):
    # Hier komt jouw code om stats en punten te updaten
    await interaction.response.send_message("Your stats have been updated!")

@tree.command(name="points", description="Check your points")
async def points(interaction: discord.Interaction):
    # Hier komt jouw code om de punten op te halen
    await interaction.response.send_message("You have X points!")

# ===== On Ready Event =====
@bot.event
async def on_ready():
    await tree.sync()  # registreer alle slash commands bij Discord
    print(f"Bot is online as {bot.user}")

# ===== Start Bot =====
bot.run(os.environ['DISCORD_TOKEN']) # vervang door je echte Discord token


import sys
import types

# Dummy audioop module to bypass missing error on Python 3.13+
sys.modules['audioop'] = types.ModuleType('audioop')

import os
import asyncio
import requests
import discord
from discord.ext import commands
import database
from pointsystem import calculate_points

# Config
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WISE_API = "https://api.wiseoldman.net/v2/players/"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Ladder ranks (threshold, name)
RANKS = [
    (0, "Bronze"),
    (1000, "Iron"),
    (2500, "Rune"),
    (5000, "Dragon"),
    (10000, "Grandmaster"),
    (20000, "Legend"),
]

# Prestige roles mapping (name -> check function name in code)
PRESTIGE_ROLES = [
    "Barrows/Enforcer", "Skillcape", "TzTok", "Quester", "Musician", "Elite",
    "126", "Achiever", "Champion", "Quiver", "TzKal", "Cape Haver", "Master",
    "Braindead", "Leaguer", "Maxed", "Clogger", "Kitted", "Pet Hunter", "Last Event Winner"
]

def get_rank(points):
    rank = "Unranked"
    for threshold, name in RANKS:
        if points >= threshold:
            rank = name
    return rank

async def fetch_wise_player(rsn: str):
    """Fetch player JSON from Wise Old Man API. Runs in a thread to avoid blocking event loop."""
    try:
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, lambda: requests.get(WISE_API + rsn, timeout=10))
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as e:
        return None

def map_wise_to_schema(wise_json: dict):
    """
    Map parts of the Wise Old Man player JSON to the simplified schema used by calculate_points().
    The mapping below is intentionally conservative (defaults to 0/False) so the bot runs out-of-the-box.
    You can improve mappings later if your Wise JSON differs.
    """
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

    try:
        # Skills & total level
        if "experience" in wise_json and isinstance(wise_json.get("experience"), dict):
            # total level might be present as 'total' in the `levels` or `experience`, try multiple fallbacks
            totals = wise_json.get("levels") or wise_json.get("experience") or {}
            total_level = totals.get("overall", {}).get("level") if isinstance(totals.get("overall"), dict) else None
            if total_level is None:
                # fallback to 'totalLevel' or 'total' fields
                total_level = wise_json.get("totalLevel") or wise_json.get("total_level") or 0
            data["skills"]["total_level"] = int(total_level or 0)
        else:
            data["skills"]["total_level"] = int(wise_json.get("totalLevel") or wise_json.get("total_level") or 0)
        # 99 checks and extras: try to count how many skills have level >=99
        try:
            ninetynines = 0
            levels = wise_json.get("levels") or {}
            if isinstance(levels, dict):
                for k,v in levels.items():
                    lvl = v.get("level") if isinstance(v, dict) else None
                    if lvl and int(lvl) >= 99:
                        ninetynines += 1
            data["skills"]["first_99"] = (ninetynines >= 1)
            if ninetynines >= 1:
                data["skills"]["extra_99s"] = max(0, ninetynines - 1)
        except Exception:
            pass

        # Boss KCs: wise JSON might have 'bosses' with 'records' or 'bossRecords'
        bosses_source = wise_json.get("bosses") or wise_json.get("bossRecords") or {}
        if isinstance(bosses_source, dict):
            # attempt to fill common boss keys (defaults to 0)
            for key in ["barrows", "zulrah", "vorkath", "gwd", "wildy", "jad", "zuk", "cox", "tob", "toa"]:
                # try a few likely name variants
                value = 0
                for variant in (key, key.capitalize(), key.upper(), key.replace("gwd","God Wars")):
                    if variant in bosses_source and isinstance(bosses_source[variant], dict):
                        value = int(bosses_source[variant].get("kc") or bosses_source[variant].get("kills") or 0)
                        break
                    elif variant in bosses_source and isinstance(bosses_source[variant], (int, float)):
                        value = int(bosses_source[variant])
                        break
                data["bosses"][key] = value

        # Diaries: try to read diary progress counts (this depends on JSON structure)
        diaries = wise_json.get("diaries") or {}
        if isinstance(diaries, dict):
            data["diaries"]["easy"] = int(diaries.get("easy", 0) or 0)
            data["diaries"]["medium"] = int(diaries.get("medium", 0) or 0)
            data["diaries"]["hard"] = int(diaries.get("hard", 0) or 0)
            data["diaries"]["elite"] = int(diaries.get("elite", 0) or 0)
            # all_completed heuristic
            if diaries.get("completed") == True or diaries.get("all", False) == True:
                data["diaries"]["all_completed"] = True

        # Achievements / capes
        achievements = wise_json.get("titles") or wise_json.get("achievements") or {}
        if isinstance(achievements, dict):
            data["achievements"]["quest_cape"] = bool(wise_json.get("hasQuestCape") or achievements.get("questCape") or achievements.get("quest_cape"))
            data["achievements"]["music_cape"] = bool(wise_json.get("hasMusicCape") or achievements.get("musicCape") or achievements.get("music_cape"))
            data["achievements"]["diary_cape"] = bool(achievements.get("diaryCape") or achievements.get("diary_cape") or wise_json.get("hasDiaryCape"))
            data["achievements"]["max_cape"] = bool(achievements.get("maxCape") or achievements.get("max_cape") or wise_json.get("isMaxed"))

        # Pets: try to read counts if available (some APIs list 'pets')
        pets = wise_json.get("pets") or {}
        if isinstance(pets, dict):
            data["pets"]["skilling"] = int(pets.get("skilling", 0) or 0)
            data["pets"]["boss"] = int(pets.get("boss", 0) or 0)
            data["pets"]["raids"] = int(pets.get("raids", 0) or 0)

    except Exception:
        pass

    return data

async def ensure_roles_exist(guild: discord.Guild):
    """Ensure ladder ranks + prestige roles exist; create them if missing (no icons)."""
    existing = {r.name: r for r in guild.roles}
    created = []
    # Ladder
    for _, name in RANKS:
        if name not in existing:
            role = await guild.create_role(name=name)
            created.append(role.name)
    # Prestige
    for pname in PRESTIGE_ROLES:
        if pname not in existing:
            role = await guild.create_role(name=pname)
            created.append(role.name)
    return created

async def assign_roles(member: discord.Member, ladder_rank_name: str, prestige_list):
    """Remove old ladder roles, add ladder+prestige roles to member."""
    # Remove existing ladder roles the member had
    ladder_names = [r[1] for r in RANKS]
    to_remove = [r for r in member.roles if r.name in ladder_names]
    if to_remove:
        await member.remove_roles(*to_remove)
    # Add ladder role
    guild_role = discord.utils.get(member.guild.roles, name=ladder_rank_name)
    if guild_role:
        await member.add_roles(guild_role)
    # Add prestige roles (if they exist)
    for p in prestige_list:
        role = discord.utils.get(member.guild.roles, name=p)
        if role and role not in member.roles:
            await member.add_roles(role)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await database.init_db()
    # Optionally ensure roles on each guild the bot is in
    for guild in bot.guilds:
        created = await ensure_roles_exist(guild)
        if created:
            print(f"Created roles in {guild.name}: {created}")

@bot.command()
async def link(ctx, *, rsn: str):
    """Link your RSN to your Discord account."""
    await database.link_player(str(ctx.author.id), rsn)
    await ctx.send(f"✅ {ctx.author.mention}, your RSN **{rsn}** has been linked. Use `!update` to fetch your points.")

@bot.command()
async def update(ctx, *, rsn: str = None):
    """
    Update the caller's points and roles.
    Optionally an admin can do `!update @user` or `!update rsn` — for simplicity this command updates the caller.
    """
    # Determine target user & rsn
    discord_id = str(ctx.author.id)
    stored = await database.get_player(discord_id)
    if not stored and not rsn:
        return await ctx.send("❌ You need to link an RSN first using `!link <rsn>` or provide an RSN in this command.")
    if rsn:
        target_rsn = rsn
    else:
        target_rsn = stored[0]

    await ctx.send("🔄 Fetching player data...")
    wise_json = await fetch_wise_player(target_rsn)
    if not wise_json:
        return await ctx.send("❌ Could not fetch player data from Wise Old Man API. Make sure the RSN is correct and try again.")

    mapped = map_wise_to_schema(wise_json)
    points = calculate_points(mapped)
    # store if linked
    if not stored:
        await database.link_player(discord_id, target_rsn)
    await database.update_points(discord_id, points)

    ladder_name = get_rank(points)
    # determine prestige roles the player qualifies for (simple heuristics)
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
    # Example boss checks
    if b.get("barrows", 0) >= 1:
        prestige_awards.append("Barrows/Enforcer")
    if b.get("zulrah", 0) >= 1 or b.get("vorkath", 0) >= 1:
        prestige_awards.append("TzTok")
    # pets heuristics
    total_pets = p.get("skilling",0) + p.get("boss",0) + p.get("raids",0)
    if total_pets >= 30:
        prestige_awards.append("Pet Hunter")

    # ensure roles exist & assign
    await ensure_roles_exist(ctx.guild)
    await assign_roles(ctx.author, ladder_name, prestige_awards)

    await ctx.send(f"✅ {ctx.author.mention} — Points: **{points}** • Ladder Rank: **{ladder_name}** • Prestige: **{', '.join(prestige_awards) if prestige_awards else 'None'}**")

@bot.command()
async def points(ctx, member: discord.Member = None):
    """Show points & rank for a member (or yourself)."""
    if member is None:
        member = ctx.author
    stored = await database.get_player(str(member.id))
    if not stored:
        return await ctx.send(f"❌ {member.mention} has not linked an RSN yet.")
    rsn, pts = stored
    rank = get_rank(pts)
    await ctx.send(f"🏆 {member.mention} | RSN: **{rsn}** | Points: **{pts}** | Rank: **{rank}**")

@bot.command()
@commands.has_permissions(administrator=True)
async def export(ctx):
    """Export leaderboard CSV for manual use (e.g., to sync in-game)."""
    lb = await database.get_leaderboard(limit=1000)
    lines = ["rsn,points"]
    for rsn, pts in lb:
        lines.append(f"{rsn},{pts}")
    csv = "\\n".join(lines)
    await ctx.send("📤 Leaderboard CSV:", file=discord.File(fp=csv.encode(), filename="leaderboard.csv"))

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN env var not set. Set it in Render (or locally) and restart.")
    else:
        bot.run(DISCORD_TOKEN)
