# database.py

import aiosqlite
import json

DB_NAME = "players.db"

# ===== Initialize DB =====
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                discord_id TEXT PRIMARY KEY,
                rsn TEXT,
                points INTEGER DEFAULT 0,
                donations INTEGER DEFAULT 0,
                boss_kc TEXT DEFAULT '{}'
            )
        """)
        await db.commit()

# ===== Link RSN =====
async def link_player(discord_id, rsn, initial_boss_kc=None):
    """
    Link a player's RSN. Optionally store initial boss KC snapshot for future calculations.
    """
    boss_kc_json = json.dumps(initial_boss_kc or {})
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO players (discord_id, rsn, points, donations, boss_kc)
            VALUES (?, ?, 0, 0, ?)
            ON CONFLICT(discord_id) DO UPDATE SET rsn=excluded.rsn, boss_kc=excluded.boss_kc
        """, (discord_id, rsn, boss_kc_json))
        await db.commit()

# ===== Update points and/or donations =====
async def update_points(discord_id, points=None, donations=None, boss_kc=None):
    """
    Update player's points, donations, and optionally boss_kc snapshot.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        if points is not None and donations is not None and boss_kc is not None:
            await db.execute(
                "UPDATE players SET points=?, donations=?, boss_kc=? WHERE discord_id=?",
                (points, donations, json.dumps(boss_kc), discord_id)
            )
        elif points is not None and donations is not None:
            await db.execute(
                "UPDATE players SET points=?, donations=? WHERE discord_id=?",
                (points, donations, discord_id)
            )
        elif points is not None:
            await db.execute(
                "UPDATE players SET points=? WHERE discord_id=?",
                (points, discord_id)
            )
        elif donations is not None:
            await db.execute(
                "UPDATE players SET donations=? WHERE discord_id=?",
                (donations, discord_id)
            )
        elif boss_kc is not None:
            await db.execute(
                "UPDATE players SET boss_kc=? WHERE discord_id=?",
                (json.dumps(boss_kc), discord_id)
            )
        await db.commit()

# ===== Get player info =====
async def get_player(discord_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT rsn, points, donations, boss_kc FROM players WHERE discord_id=?",
            (discord_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                rsn, points, donations, boss_kc_json = row
                boss_kc = json.loads(boss_kc_json or '{}')
                return rsn, points, donations, boss_kc
            return None

# ===== Get points only =====
async def get_points(discord_id):
    player = await get_player(discord_id)
    if player:
        return player[1]  # points
    return 0

# ===== Get donations only =====
async def get_donations(discord_id):
    player = await get_player(discord_id)
    if player:
        return player[2]  # donations
    return 0

# ===== Get leaderboard =====
async def get_leaderboard(limit=10):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT rsn, points, donations FROM players ORDER BY points DESC LIMIT ?",
            (limit,)
        ) as cur:
            return await cur.fetchall()

# ===== Get donator leaderboard =====
async def get_donator_leaderboard(limit=10):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT rsn, donations FROM players ORDER BY donations DESC LIMIT ?",
            (limit,)
        ) as cur:
            return await cur.fetchall()
