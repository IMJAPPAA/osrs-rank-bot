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

PRESTIGE_ROLES = [
    "Quester", "Musician", "Achiever", "Maxed", "Elite", "126",
    "Barrows/Enforcer", "TzTok", "Pet Hunter"
]

# ===== Bot & Slash Command Tree =====
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ===== Points System =====
def calculate_points(mapped: dict):
    points = 0
    total_lvl = mapped["skills"]["total_level"]
    # Total level points
    if total_lvl < 1000: points += 25
    elif total_lvl < 1500: points += 30
    elif total_lvl < 1750: points += 35
    elif total_lvl < 2000: points += 40
    elif total_lvl < 2200: points += 45
    else: points += 50

    # Bosses per 100 KC
    bosses = mapped.get("bosses", {})
    points += (bosses.get("barrows",0)//100)*10
    points += (bosses.get("zulrah",0)//100)*25
    points += (bosses.get("vorkath",0)//100)*30
    points += (bosses.get("gwd",0)//100)*40
    points += (bosses.get("wildy",0)//100)*50

    # First-time kills
    points += mapped.get("first_time_kills",0)*10

    # Special bosses
    points += bosses.get("jad",0)*25
    points += bosses.get("zuk",0)*150

    # Raids
    raids = mapped.get("pets",{})  # Raid clears stored in pets.raids
    points += raids.get("raids",0)*75

    # Diaries
    diaries = mapped.get("diaries",{})
    if diaries.get("easy",0)>0: points += 5
    if diaries.get("medium",0)>0: points += 10
    if diaries.get("hard",0)>0: points += 20
    if diaries.get("elite",0)>0: points += 40
    if diaries.get("all_completed",False): points += 50

    # Achievements
    ach = mapped.get("achievements",{})
    if ach.get("quest_cape"): points += 75
    if ach.get("music_cape"): points += 25
    if ach.get("diary_cape"): points += 100
    if ach.get("max_cape"): points += 300

    # Skills
    if mapped["skills"].get("first_99",False): points += 50
    points += mapped["skills"].get("extra_99s",0)*25
    if total_lvl >= 2277: points += 200
    if ach.get("max_cape"): points += 300

    # Pets
    pets = mapped.get("pets",{})
    points += pets.get("skilling",0)*25
    points += pets.get("boss",0)*50
    points += pets.get("raids",0)*75

    # Events & Donations
    events = mapped.get("events",{})
    points += events.get("pvm_participations",0)*10
    points += events.get("event_wins",0)*15
    donations = mapped.get("donations",0)
    if donations < 25_000_000: points += 10
    elif donations < 50_000_000: points += 20
    elif donations < 100_000_000: points += 40
    elif donations < 200_000_000: points += 80
    else: points += 150

    return points

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
        print(f"Error fetching RSN {rsn} from WOM: {e}")
        return None

async def map_wise_to_schema(wise_json: dict):
    data = {
        "bosses": {},
        "diaries": {"easy":0,"medium":0,"hard":0,"elite":0,"all_completed":False},
        "achievements": {"quest_cape":False,"music_cape":False,"diary_cape":False,"max_cape":False},
        "skills":{"first_99":False,"extra_99s":0,"total_level":0},
        "pets":{"skilling":0,"boss":0,"raids":0},
        "events":{"pvm_participations":0,"event_wins":0},
        "donations":0,
        "first_time_kills":0
    }
    levels = wise_json.get("levels",{})
    data["skills"]["total_level"] = int(levels.get("overall",{}).get("level",0) or 0)
    ninetynines = sum(1 for v in levels.values() if isinstance(v, dict) and v.get("level",0)>=99)
    data["skills"]["first_99"] = ninetynines>=1
    data["skills"]["extra_99s"] = max(0,ninetynines-1)

    bosses_source = wise_json.get("bosses",{})
    for key in ["barrows","zulrah","vorkath","gwd","wildy","jad","zuk","cox","tob","toa"]:
        data["bosses"][key] = int(bosses_source.get(key,0) or 0)

    diaries = wise_json.get("diaries",{})
    data["diaries"]["easy"] = int(diaries.get("easy",0) or 0)
    data["diaries"]["medium"] = int(diaries.get("medium",0) or 0)
    data["diaries"]["hard"] = int(diaries.get("hard",0) or 0)
    data["diaries"]["elite"] = int(diaries.get("elite",0) or 0)
    data["diaries"]["all_completed"] = diaries.get("completed",False)

    ach = wise_json.get("achievements",{})
    data["achievements"]["quest_cape"] = bool(ach.get("questCape") or wise_json.get("hasQuestCape"))
    data["achievements"]["music_cape"] = bool(ach.get("musicCape") or wise_json.get("hasMusicCape"))
    data["achievements"]["diary_cape"] = bool(ach.get("diaryCape") or wise_json.get("hasDiaryCape"))
    data["achievements"]["max_cape"] = bool(ach.get("maxCape") or wise_json.get("isMaxed"))

    pets = wise_json.get("pets",{})
    data["pets"]["skilling"] = int(pets.get("skilling",0) or 0)
    data["pets"]["boss"] = int(pets.get("boss",0) or 0)
    data["pets"]["raids"] = int(pets.get("raids",0) or 0)
    return data

# ===== Roles Helper Functions =====
async def ensure_roles_exist(guild: discord.Guild):
    existing = {r.name: r for r in guild.roles}
    created = []
    for _, name in RANKS + [(0,p) for p in PRESTIGE_ROLES]:
        if name not in existing:
            role = await guild.create_role(name=name)
            created.append(role.name)
    return created

async def assign_roles(member: discord.Member, ladder_rank_name: str, prestige_list: list[str]):
    ladder_names = [r[1] for r in RANKS]
    to_remove = [r for r in member.roles if r.name in ladder_names and r.name != ladder_rank_name]
    if to_remove:
        await member.remove_roles(*to_remove)
    ladder_role = discord.utils.get(member.guild.roles, name=ladder_rank_name)
    if ladder_role and ladder_role not in member.roles:
        await member.add_roles(ladder_role)
    for prestige_name in prestige_list:
        prestige_role = discord.utils.get(member.guild.roles, name=prestige_name)
        if prestige_role and prestige_role not in member.roles:
            await member.add_roles(prestige_role)

# ===== Admin/Owner Check =====
def is_admin_or_owner():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator or interaction.user==interaction.guild.owner
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
        return await interaction.response.send_message("❌ Link an RSN first with `/link <rsn>` or provide RSN.")
    target_rsn = rsn if rsn else stored[0]
    await interaction.response.defer(thinking=True)
    wise_json = await fetch_wise_player(target_rsn)
    if not wise_json:
        return await interaction.followup.send(f"❌ Could not fetch player data from Wise Old Man for `{target_rsn}`.")
    mapped = await map_wise_to_schema(wise_json)
    base_points = calculate_points(mapped)
    manual_points = 0
    if stored:
        _, current_points = stored
        manual_points = max(0, current_points - base_points)
    total_points = base_points + manual_points
    if not stored: await database.link_player(discord_id, target_rsn)
    await database.update_points(discord_id, total_points)
    ladder_name = get_rank(total_points)

    # Prestige awards
    prestige_awards = []
    a = mapped.get("achievements",{})
    d = mapped.get("diaries",{})
    s = mapped.get("skills",{})
    p = mapped.get("pets",{})
    b = mapped.get("bosses",{})

    if a.get("quest_cape"): prestige_awards.append("Quester")
    if a.get("music_cape"): prestige_awards.append("Musician")
    if d.get("diary_cape") or d.get("all_completed"): prestige_awards.append("Achiever")
    if a.get("max_cape"): prestige_awards.append("Maxed")
    if d.get("elite",0)>=1: prestige_awards.append("Elite")
    if s.get("total_level",0)>=126: prestige_awards.append("126")
    if b.get("barrows",0)>=10: prestige_awards.append("Barrows/Enforcer")
    if b.get("zulrah",0)>=1 or b.get("vorkath",0)>=1: prestige_awards.append("TzTok")
    total_pets = p.get("skilling",0)+p.get("boss",0)+p.get("raids",0)
    if total_pets>=10: prestige_awards.append("Pet Hunter")

    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards)
    prestige_text = ', '.join(prestige_awards) if prestige_awards else 'None'
    await interaction.followup.send(f"✅ {interaction.user.mention} — Points: **{total_points}** • Ladder Rank: **{ladder_name}** • Prestige: **{prestige_text}**")

# ===== /points, /requestpoint, /approve, /addpoints =====
# ... Implement these commands as in previous version, now using calculate_points function

@bot.event
async def on_ready():
    await database.init_db()
    await tree.sync()
    for guild in bot.guilds:
        created = await ensure_roles_exist(guild)
        if created: print(f"Created roles in {guild.name}: {created}")
    print(f"✅ Bot is online as {bot.user} and commands are synced globally")

if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN env var not set.")
else:
    bot.run(DISCORD_TOKEN)
