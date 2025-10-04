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
                wom_points INTEGER DEFAULT 0,
                discord_points INTEGER DEFAULT 0,
                donations INTEGER DEFAULT 0,
                boss_kc_at_link TEXT DEFAULT '{}'
            )
        """)
        await db.commit()

# ===== Link RSN =====
async def link_player(discord_id, rsn, boss_kc_at_link="{}"):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO players (discord_id, rsn, wom_points, discord_points, donations, boss_kc_at_link)
            VALUES (?, ?, 0, 0, 0, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                rsn=excluded.rsn,
                boss_kc_at_link=excluded.boss_kc_at_link
        """, (discord_id, rsn, boss_kc_at_link))
        await db.commit()

# ===== Update points =====
async def update_points(discord_id, wom_points=None, discord_points=None, donations=None, boss_kc_at_link=None):
    async with aiosqlite.connect(DB_NAME) as db:
        query = "UPDATE players SET "
        params = []
        if wom_points is not None:
            query += "wom_points=?, "
            params.append(wom_points)
        if discord_points is not None:
            query += "discord_points=?, "
            params.append(discord_points)
        if donations is not None:
            query += "donations=?, "
            params.append(donations)
        if boss_kc_at_link is not None:
            query += "boss_kc_at_link=?, "
            params.append(boss_kc_at_link)
        if not params:
            return
        query = query.rstrip(", ") + " WHERE discord_id=?"
        params.append(discord_id)
        await db.execute(query, tuple(params))
        await db.commit()

# ===== Get player info =====
async def get_player(discord_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT rsn, wom_points, discord_points, donations, boss_kc_at_link FROM players WHERE discord_id=?",
            (discord_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row
            return None

# ===== Get total points =====
async def get_total_points(discord_id):
    player = await get_player(discord_id)
    if player:
        rsn, wom_points, discord_points, donations, _ = player
        return wom_points + discord_points + donations
    return 0
