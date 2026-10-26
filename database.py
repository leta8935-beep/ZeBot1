import asyncpg

class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            self.dsn, min_size=1, max_size=5,
            statement_cache_size=0, max_cached_statement_lifetime=0
        )
        async with self.pool.acquire() as c:
            await c.execute("""
            CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, wallet BIGINT NOT NULL DEFAULT 500);
            CREATE TABLE IF NOT EXISTS transactions (id SERIAL PRIMARY KEY, from_id BIGINT, to_id BIGINT, amount BIGINT NOT NULL, kind TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS passports (
                user_id BIGINT PRIMARY KEY, surname TEXT NOT NULL, name TEXT NOT NULL, patronymic TEXT NOT NULL,
                dob TEXT NOT NULL, pob TEXT NOT NULL, bio TEXT NOT NULL, photo_url TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS guild_settings (guild_id BIGINT PRIMARY KEY, review_channel_id BIGINT, start_roles TEXT);
            CREATE TABLE IF NOT EXISTS organizations (
                org_id SERIAL PRIMARY KEY, owner_id BIGINT NOT NULL, name TEXT NOT NULL,
                org_type TEXT DEFAULT 'Бизнес', sphere TEXT DEFAULT 'Не указана', level INT DEFAULT 1,
                balance BIGINT DEFAULT 0, logo_url TEXT DEFAULT '', last_collect DOUBLE PRECISION DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS org_members (
                org_id INT, user_id BIGINT, rank TEXT DEFAULT 'Сотрудник',
                PRIMARY KEY (org_id, user_id)
            );
            """)
            await c.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS state_name TEXT DEFAULT 'РОССИЙСКАЯ ФЕДЕРАЦИЯ';")
            await c.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS state_name_en TEXT DEFAULT 'RUSSIAN FEDERATION';")
            await c.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS state_code TEXT DEFAULT 'RUS';")
            await c.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'RUB';")
            await c.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS manager_id BIGINT;")
            await c.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS curator_role BIGINT;")
            await c.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS mod_role BIGINT;")
            await c.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS admin_role BIGINT;")
            await c.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS pr_role BIGINT;")

    async def get_user(self, user_id: int):
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
            return await c.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)

    async def update_wallet(self, user_id: int, delta: int):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE users SET wallet = GREATEST(wallet + $1, 0) WHERE user_id=$2", delta, user_id)

    async def set_wallet(self, user_id: int, amount: int):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE users SET wallet = $1 WHERE user_id=$2", amount, user_id)

    async def log(self, from_id, to_id, amount, kind):
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO transactions (from_id, to_id, amount, kind) VALUES ($1,$2,$3,$4)", from_id, to_id, amount, kind)

    async def get_user_organizations(self, owner_id: int):
        async with self.pool.acquire() as c:
            return await c.fetch("SELECT * FROM organizations WHERE owner_id=$1 ORDER BY org_id", owner_id)

    async def get_organization(self, org_id: int):
        async with self.pool.acquire() as c:
            return await c.fetchrow("SELECT * FROM organizations WHERE org_id=$1", org_id)

    async def get_all_organizations(self):
        async with self.pool.acquire() as c:
            return await c.fetch("SELECT * FROM organizations ORDER BY org_id")

    async def create_organization(self, owner_id: int, name: str, org_type: str, sphere: str, logo_url: str):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                "INSERT INTO organizations (owner_id, name, org_type, sphere, logo_url) VALUES ($1,$2,$3,$4,$5) RETURNING *",
                owner_id, name, org_type, sphere, logo_url
            )

    async def update_organization(self, org_id: int, level: int = None, balance: int = None, last_collect: float = None):
        async with self.pool.acquire() as c:
            if level is not None: await c.execute("UPDATE organizations SET level=$1 WHERE org_id=$2", level, org_id)
            if balance is not None: await c.execute("UPDATE organizations SET balance=$1 WHERE org_id=$2", balance, org_id)
            if last_collect is not None: await c.execute("UPDATE organizations SET last_collect=$1 WHERE org_id=$2", last_collect, org_id)

    async def add_to_org_balance(self, org_id: int, amount: int):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE organizations SET balance = balance + $1 WHERE org_id=$2", amount, org_id)

    async def delete_organization(self, org_id: int):
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM org_members WHERE org_id=$1", org_id)
            await c.execute("DELETE FROM organizations WHERE org_id=$1", org_id)

    async def add_org_member(self, org_id: int, user_id: int, rank: str = 'Сотрудник'):
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO org_members (org_id, user_id, rank) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING", org_id, user_id, rank)

    async def remove_org_member(self, org_id: int, user_id: int):
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM org_members WHERE org_id=$1 AND user_id=$2", org_id, user_id)

    async def get_org_members(self, org_id: int):
        async with self.pool.acquire() as c:
            return await c.fetch("SELECT * FROM org_members WHERE org_id=$1", org_id)

    async def save_passport(self, user_id, surname, name, patronymic, dob, pob, bio, photo_url):
        async with self.pool.acquire() as c:
            await c.execute("""
                INSERT INTO passports (user_id, surname, name, patronymic, dob, pob, bio, photo_url)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (user_id) DO UPDATE SET surname=$2, name=$3, patronymic=$4, dob=$5, pob=$6, bio=$7, photo_url=$8
            """, user_id, surname, name, patronymic, dob, pob, bio, photo_url)

    async def get_passport(self, user_id: int):
        async with self.pool.acquire() as c:
            return await c.fetchrow("SELECT * FROM passports WHERE user_id=$1", user_id)

    async def update_passport_field(self, user_id: int, field: str, value: str):
        allowed = ["surname", "name", "patronymic", "dob", "pob", "bio", "photo_url"]
        if field not in allowed: return False
        async with self.pool.acquire() as c:
            await c.execute(f"UPDATE passports SET {field}=$1 WHERE user_id=$2", value, user_id)
        return True

    async def set_guild_setting(self, guild_id: int, column: str, value):
        allowed = ["review_channel_id", "start_roles", "curator_role", "mod_role", "admin_role", "pr_role", "manager_id", "state_name", "state_name_en", "state_code", "currency"]
        if column not in allowed: return
        async with self.pool.acquire() as c:
            exists = await c.fetchval("SELECT 1 FROM guild_settings WHERE guild_id=$1", guild_id)
            if not exists: await c.execute("INSERT INTO guild_settings (guild_id) VALUES ($1)", guild_id)
            await c.execute(f"UPDATE guild_settings SET {column}=$1 WHERE guild_id=$2", value, guild_id)

    async def get_guild_settings(self, guild_id: int):
        async with self.pool.acquire() as c:
            return await c.fetchrow("SELECT * FROM guild_settings WHERE guild_id=$1", guild_id)
