# database.py

import aiosqlite

DB_NAME = "players.db"

# ===== Initialize DB =====
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                discord_id TEXT PRIMARY KEY,
                rsn TEXT,
                points INTEGER DEFAULT 0,
                donations INTEGER DEFAULT 0
            )
        """)
        await db.commit()

# ===== Link RSN =====
async def link_player(discord_id, rsn):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO players (discord_id, rsn, points, donations)
            VALUES (?, ?, 0, 0)
            ON CONFLICT(discord_id) DO UPDATE SET rsn=excluded.rsn
        """, (discord_id, rsn))
        await db.commit()

# ===== Update points and/or donations =====
async def update_points(discord_id, points=None, donations=None):
    async with aiosqlite.connect(DB_NAME) as db:
        if points is not None and donations is not None:
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
        await db.commit()

# ===== Get player info =====
async def get_player(discord_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT rsn, points, donations FROM players WHERE discord_id=?",
            (discord_id,)
        ) as cur:
            return await cur.fetchone()

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
