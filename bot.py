# ===== Dummy audioop module =====
import sys, types
sys.modules['audioop'] = types.ModuleType('audioop')

# ===== Imports =====
import os, asyncio, requests, discord, re, urllib.parse
from discord.ext import commands
from discord import app_commands
import database  # jouw database.py
from pointsystem import calculate_points  # jouw puntensysteem

# ===== Config =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WISE_API = "https://api.wiseoldman.net/v2/players/"

# ===== Ladder & Prestige Roles =====
RANKS = [
    (0, "Bronze"),
    (1000, "Iron"),
    (2500, "Rune"),
    (5000, "Dragon"),
    (10000, "Grandmaster"),
    (20000, "Legend"),
]

PRESTIGE_ROLES = [
    "Quester", "Musician", "Achiever", "Maxed", "Elite",
    "126", "Barrows/Enforcer", "TzTok", "Pet Hunter"
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
        "bosses": {}, "diaries": {}, "achievements": {}, "skills": {}, "pets": {}
    }
    # Mapping similar aan jouw eerdere setup, vul levels, bosses, diaries, achievements, pets
    levels = wise_json.get("levels") or wise_json.get("experience") or {}
    overall_level = int(levels.get("overall", {}).get("level", 0) or 0)
    data["skills"]["total_level"] = overall_level
    ninetynines = sum(1 for v in levels.values() if isinstance(v, dict) and v.get("level",0)>=99)
    data["skills"]["first_99"] = ninetynines>=1
    data["skills"]["extra_99s"] = max(0, ninetynines-1)

    bosses = wise_json.get("bosses") or wise_json.get("bossRecords") or {}
    for b in ["barrows","zulrah","vorkath","gwd","wildy","jad","zuk","cox","tob","toa"]:
        data["bosses"][b] = int(bosses.get(b,0) or 0)
    
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

    pets = wise_json.get("pets") or {}
    data["pets"]["skilling"] = int(pets.get("skilling",0) or 0)
    data["pets"]["boss"] = int(pets.get("boss",0) or 0)
    data["pets"]["raids"] = int(pets.get("raids",0) or 0)

    return data

async def ensure_roles_exist(guild: discord.Guild):
    existing = {r.name: r for r in guild.roles}
    created = []
    for _, name in RANKS + [(0,p) for p in PRESTIGE_ROLES]:
        if name not in existing:
            role = await guild.create_role(name=name)
            created.append(name)
    return created

async def assign_roles(member: discord.Member, ladder_name: str, prestige_list: list[str]):
    # Ladder
    ladder_names = [r[1] for r in RANKS]
    to_remove = [r for r in member.roles if r.name in ladder_names]
    if to_remove:
        await member.remove_roles(*to_remove)
    ladder_role = discord.utils.get(member.guild.roles, name=ladder_name)
    if ladder_role and ladder_role not in member.roles:
        await member.add_roles(ladder_role)
    # Prestige
    for pname in PRESTIGE_ROLES:
        role = discord.utils.get(member.guild.roles, name=pname)
        if role and pname in prestige_list and role not in member.roles:
            await member.add_roles(role)
        elif role and pname not in prestige_list and role in member.roles:
            await member.remove_roles(role)

# Admin/Owner check
def is_admin_or_owner():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator or interaction.user == interaction.guild.owner
    return app_commands.check(predicate)

# ===== Slash Commands =====
@tree.command(name="link", description="Link your OSRS account")
async def link(interaction: discord.Interaction, rsn: str):
    await database.link_player(str(interaction.user.id), rsn)
    await interaction.response.send_message(f"✅ {interaction.user.mention}, your RSN **{rsn}** linked. Use `/update` to fetch points.")

@tree.command(name="update", description="Update your points and roles")
async def update(interaction: discord.Interaction, rsn: str = None):
    discord_id = str(interaction.user.id)
    stored = await database.get_player(discord_id)
    if not stored and not rsn:
        return await interaction.response.send_message("❌ Link first with `/link <rsn>` or provide RSN.")
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
    await database.update_points(discord_id, total_points)
    ladder_name = get_rank(total_points)

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
    if d.get("elite",0)>=1: prestige_awards.append("Elite")
    if s.get("total_level",0)>=126: prestige_awards.append("126")
    if b.get("barrows",0)>=10: prestige_awards.append("Barrows/Enforcer")
    if b.get("zulrah",0)>=1 or b.get("vorkath",0)>=1: prestige_awards.append("TzTok")
    total_pets = p.get("skilling",0)+p.get("boss",0)+p.get("raids",0)
    if total_pets >= 10: prestige_awards.append("Pet Hunter")

    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards)
    await interaction.followup.send(f"✅ {interaction.user.mention} — Points: **{total_points}** • Rank: **{ladder_name}** • Prestige: {', '.join(prestige_awards) if prestige_awards else 'None'}")

@tree.command(name="points", description="Check points and rank")
async def points(interaction: discord.Interaction, member: discord.Member = None):
    if not member:
        member = interaction.user
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.response.send_message(f"❌ {member.mention} has not linked RSN.")
    rsn, pts = stored
    await interaction.response.send_message(f"🏆 {member.mention} | RSN: **{rsn}** | Points: **{pts}** | Rank: **{get_rank(pts)}**")

@tree.command(name="addpoints", description="Add points to a user (Admin/Owner only)")
@is_admin_or_owner()
async def addpoints(interaction: discord.Interaction, member: discord.Member, points: int):
    await interaction.response.defer(thinking=True)
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.followup.send(f"❌ {member.mention} has not linked RSN.")
    rsn, current_points = stored
    new_points = current_points + points
    await database.update_points(str(member.id), new_points)

    wise_json = await fetch_wise_player(rsn)
    mapped = await map_wise_to_schema(wise_json) if wise_json else {}
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
    if d.get("elite",0)>=1: prestige_awards.append("Elite")
    if s.get("total_level",0)>=126: prestige_awards.append("126")
    if b.get("barrows",0)>=10: prestige_awards.append("Barrows/Enforcer")
    if b.get("zulrah",0)>=1 or b.get("vorkath",0)>=1: prestige_awards.append("TzTok")
    total_pets = p.get("skilling",0)+p.get("boss",0)+p.get("raids",0)
    if total_pets >= 10: prestige_awards.append("Pet Hunter")

    ladder_name = get_rank(new_points)
    await assign_roles(member, ladder_name, prestige_awards)
    await interaction.followup.send(f"✅ {points} points added to {member.mention}. Total points: {new_points}")

@tree.command(name="sync", description="Sync a user's RSN and update points/roles (Admin/Owner only)")
@is_admin_or_owner()
async def sync(interaction: discord.Interaction, rsn: str, member: discord.Member):
    await interaction.response.defer(thinking=True)
    wise_json = await fetch_wise_player(rsn)
    if not wise_json:
        return await interaction.followup.send(f"❌ Could not fetch RSN `{rsn}`")
    mapped = await map_wise_to_schema(wise_json)
    total_points = calculate_points(mapped)

    await database.link_player(str(member.id), rsn)
    await database.update_points(str(member.id), total_points)

    ladder_name = get_rank(total_points)
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
    if d.get("elite",0)>=1: prestige_awards.append("Elite")
    if s.get("total_level",0)>=126: prestige_awards.append("126")
    if b.get("barrows",0)>=10: prestige_awards.append("Barrows/Enforcer")
    if b.get("zulrah",0)>=1 or b.get("vorkath",0)>=1: prestige_awards.append("TzTok")
    total_pets = p.get("skilling",0)+p.get("boss",0)+p.get("raids",0)
    if total_pets >= 10: prestige_awards.append("Pet Hunter")

    await ensure_roles_exist(member.guild)
    await assign_roles(member, ladder_name, prestige_awards)
    await interaction.followup.send(f"✅ {member.mention} synced — Points: **{total_points}** • Rank: **{ladder_name}** • Prestige: {', '.join(prestige_awards) if prestige_awards else 'None'}")

# ===== On Ready =====
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
