import aiosqlite

DB_NAME = "players.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                discord_id TEXT PRIMARY KEY,
                rsn TEXT,
                points INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def link_player(discord_id, rsn):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO players (discord_id, rsn)
            VALUES (?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET rsn=excluded.rsn
        """, (discord_id, rsn))
        await db.commit()

async def update_points(discord_id, points):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE players SET points=? WHERE discord_id=?", (points, discord_id))
        await db.commit()

async def get_player(discord_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT rsn, points FROM players WHERE discord_id=?", (discord_id,)) as cur:
            row = await cur.fetchone()
            return row

async def get_leaderboard(limit=10):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT rsn, points FROM players ORDER BY points DESC LIMIT ?", (limit,)) as cur:
            rows = await cur.fetchall()
            return rows
