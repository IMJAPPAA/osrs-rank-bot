import aiosqlite
import json

DB_NAME = "players.db"

# ===== Initialize DB =====
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Bestaande tabel
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                discord_id TEXT PRIMARY KEY,
                rsn TEXT,
                points INTEGER DEFAULT 0,
                donations INTEGER DEFAULT 0
            )
        """)
        # Nieuwe kolom voor boss KC bij link (veilig toevoegen)
        try:
            await db.execute("""
                ALTER TABLE players
                ADD COLUMN boss_kc_at_link TEXT DEFAULT '{}'
            """)
        except aiosqlite.OperationalError:
            # Kolom bestaat al
            pass
        await db.commit()

# ===== Link RSN =====
async def link_player(discord_id, rsn, boss_kc_at_link="{}"):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO players (discord_id, rsn, points, donations, boss_kc_at_link)
            VALUES (?, ?, 0, 0, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                rsn=excluded.rsn,
                boss_kc_at_link=excluded.boss_kc_at_link
        """, (discord_id, rsn, boss_kc_at_link))
        await db.commit()

# ===== Update points and/or donations =====
async def update_points(discord_id, points=None, donations=None, boss_kc_at_link=None):
    async with aiosqlite.connect(DB_NAME) as db:
        query = "UPDATE players SET "
        params = []
        if points is not None:
            query += "points=?, "
            params.append(points)
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
            "SELECT rsn, points, donations, boss_kc_at_link FROM players WHERE discord_id=?",
            (discord_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row  # rsn, points, donations, boss_kc_at_link
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
