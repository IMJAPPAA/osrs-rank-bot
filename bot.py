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
    """Fetch player from Wise Old Man API safely"""
    try:
        loop = asyncio.get_running_loop()
        url = WISE_API + urllib.parse.quote(rsn)
        resp = await loop.run_in_executor(None, lambda: requests.get(url, timeout=10))
        if resp.status_code != 200:
            print(f"WOM API returned status {resp.status_code} for RSN {rsn}")
            return None
        return resp.json()
    except Exception as e:
        print(f"Error fetching RSN {rsn} from WOM: {e}")
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
    for pname in PRESTIGE_ROLES:
        if pname not in existing:
            role = await guild.create_role(name=pname)
            created.append(role.name)
    return created

async def assign_roles(member: discord.Member, ladder_rank_name: str, prestige_list: list[str]):
    # ---- LADDER ROLE ----
    ladder_names = [r[1] for r in RANKS]
    to_remove = [r for r in member.roles if r.name in ladder_names]
    if to_remove:
        await member.remove_roles(*to_remove)
    ladder_role = discord.utils.get(member.guild.roles, name=ladder_rank_name)
    if ladder_role and ladder_role not in member.roles:
        await member.add_roles(ladder_role)

    # ---- PRESTIGE ROLES ----
    for prestige_name in prestige_list:
        prestige_role = discord.utils.get(member.guild.roles, name=prestige_name)
        if prestige_role and prestige_role not in member.roles:
            await member.add_roles(prestige_role)

# ===== Admin/Owner Check =====
def is_admin_or_owner():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        if interaction.user == interaction.guild.owner:
            return True
        return False
    return app_commands.check(predicate)

# ===== Slash Commands =====
@tree.command(name="link", description="Link your OSRS account")
async def link(interaction: discord.Interaction, rsn: str):
    await database.link_player(str(interaction.user.id), rsn)
    await interaction.response.send_message(
        f"✅ {interaction.user.mention}, your RSN **{rsn}** has been linked. Use `/update` to fetch your points."
    )

@tree.command(name="update", description="Update your points and roles")
async def update(interaction: discord.Interaction, rsn: str = None):
    discord_id = str(interaction.user.id)
    stored = await database.get_player(discord_id)
    if not stored and not rsn:
        return await interaction.response.send_message(
            "❌ Je moet eerst een RSN linken met `/link <rsn>` of een RSN opgeven."
        )

    target_rsn = rsn if rsn else stored[0]
    await interaction.response.defer(thinking=True)

    wise_json = await fetch_wise_player(target_rsn)
    if not wise_json:
        return await interaction.followup.send(
            f"❌ Could not fetch player data from Wise Old Man. Check RSN `{target_rsn}` of probeer later opnieuw."
        )

    mapped = await map_wise_to_schema(wise_json)
    base_points = calculate_points(mapped)

    manual_points = 0
    if stored:
        _, current_points = stored
        manual_points = max(0, current_points - base_points)

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
    if d.get("elite", 0) >= 1: prestige_awards.append("Elite")
    if s.get("total_level", 0) >= 2277: prestige_awards.append("126")
    if b.get("barrows", 0) >= 1: prestige_awards.append("Barrows/Enforcer")
    if b.get("zulrah", 0) >= 1 or b.get("vorkath", 0) >= 1: prestige_awards.append("TzTok")
    total_pets = p.get("skilling",0) + p.get("boss",0) + p.get("raids",0)
    if total_pets >= 30: prestige_awards.append("Pet Hunter")

    await ensure_roles_exist(interaction.guild)
    await assign_roles(interaction.user, ladder_name, prestige_awards)

    prestige_text = ', '.join(prestige_awards) if prestige_awards else 'None'
    await interaction.followup.send(
        f"✅ {interaction.user.mention} — Points: **{total_points}** • "
        f"Ladder Rank: **{ladder_name}** • Prestige: **{prestige_text}**"
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

# ===== /requestpoint & Admin Approve =====
@tree.command(name="requestpoint", description="Request points for your account")
async def requestpoint(interaction: discord.Interaction, rsn: str, amount: int):
    await interaction.response.defer(thinking=True)
    if amount <= 0:
        return await interaction.followup.send("❌ Points must be greater than 0.")
    
    discord_id = str(interaction.user.id)
    await database.add_point_request(discord_id, rsn, amount)
    await interaction.followup.send(
        f"📨 {interaction.user.mention}, your request for **{amount} points** for RSN `{rsn}` has been submitted. An admin will review it."
    )

@tree.command(name="requests", description="View pending point requests (Admin/Owner only)")
@is_admin_or_owner()
async def requests(interaction: discord.Interaction):
    pending = await database.get_pending_requests()
    if not pending:
        return await interaction.response.send_message("✅ No pending requests.")
    
    msg = "📋 **Pending Requests:**\n"
    for r in pending:
        msg += f"ID: {r['id']} | RSN: {r['rsn']} | Points: {r['points']} | User ID: {r['discord_id']} | Created: {r['created_at']}\n"
    
    await interaction.response.send_message(msg)

@tree.command(name="approve", description="Approve a point request (Admin/Owner only)")
@is_admin_or_owner()
async def approve(interaction: discord.Interaction, request_id: int):
    pending = await database.get_pending_requests()
    req = next((r for r in pending if r['id'] == request_id), None)
    if not req:
        return await interaction.response.send_message(f"❌ Request ID {request_id} not found.")
    
    member = interaction.guild.get_member(int(req['discord_id']))
    if member:
        stored = await database.get_player(req['discord_id'])
        current_points = stored[1] if stored else 0
        new_points = current_points + req['points']
        await database.update_points(req['discord_id'], new_points)
        
        # Update ladder/prestige roles
        wise_json = await fetch_wise_player(stored[0])
        if wise_json:
            mapped = await map_wise_to_schema(wise_json)
            ladder_name = get_rank(new_points)
            
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
            
            await assign_roles(member, ladder_name, prestige_awards)

    await database.update_request_status(request_id, "approved")
    await interaction.response.send_message(f"✅ Request ID {request_id} approved and points added.")

# ===== /addpoints (Admin/Owner only) =====
@tree.command(name="addpoints", description="Add points to a user (Admin or Owner only)")
@is_admin_or_owner()
async def addpoints(interaction: discord.Interaction, member: discord.Member, points: int):
    await interaction.response.defer(thinking=True)
    stored = await database.get_player(str(member.id))
    if not stored:
        return await interaction.followup.send(f"❌ {member.mention} has not linked an RSN yet.")

    rsn, current_points = stored
    new_points = current_points + points
    await database.update_points(str(member.id), new_points)

    wise_json = await fetch_wise_player(rsn)
    prestige_awards = []
    ladder_name = get_rank(new_points)
    if wise_json:
        mapped = await map_wise_to_schema(wise_json)
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
        
        await assign_roles(member, ladder_name, prestige_awards)

    await interaction.followup.send(f"✅ {points} points added to {member.mention}. Total points: {new_points}")

# ===== On Ready Event =====
@bot.event
async def on_ready():
    await database.init_db()
    await tree.sync()
    for guild in bot.guilds:
        created = await ensure_roles_exist(guild)
        if created:
            print(f"Created roles in {guild.name}: {created}")
    print(f"✅ Bot is online as {bot.user} and commands are synced globally")

# ===== Start Bot =====
if not DISCORD_TOKEN:
    print("ERROR: DISCORD_TOKEN env var not set. Set het lokaal of op Render en restart.")
else:
    bot.run(DISCORD_TOKEN)
