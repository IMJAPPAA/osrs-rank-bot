# OSRS Rank Bot (basic)

This is a basic Discord bot that:
- Links a user's RSN (`!link <rsn>`)
- Fetches OSRS/Wise Old Man data (`!update`) and calculates points using a custom points system
- Assigns a single ladder rank (Bronze -> Legend) and adds prestige roles for milestones
- Exports leaderboard CSV (`!export` - admin only)

## Quick setup (Render)

1. Create a GitHub repo and push this project.
2. Create a Discord bot in the Developer Portal and copy the token.
3. On Render.com create a new **Web Service**, connect your repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `python bot.py`
4. Add an Environment Variable on Render: `DISCORD_TOKEN` = *your token*
5. Deploy. Use `!link <RSN>` then `!update` in your server to test.

## Notes & Next steps
- The Wise Old Man JSON mapping in `bot.py` is intentionally conservative. If some fields are missing or named differently you may need to adjust `map_wise_to_schema()`.
- The bot auto-creates ladder + prestige roles if they are missing (no icons). You can later edit role colors/icons through Discord server settings.
- Consider upgrading Render to a paid plan for 24/7 uptime (free services sleep after inactivity).

If you want, I can also push this repo to GitHub for you (if you share access) or walk you through the Render UI step-by-step.
