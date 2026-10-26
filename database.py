import asyncpg


class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=1,
            max_size=5,
            statement_cache_size=0,
            max_cached_statement_lifetime=0,
        )
        async with self.pool.acquire() as c:
            await c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                wallet BIGINT NOT NULL DEFAULT 500
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                from_id BIGINT,
                to_id BIGINT,
                amount BIGINT NOT NULL,
                kind TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS passports (
                user_id BIGINT PRIMARY KEY,
                surname TEXT NOT NULL,
                name TEXT NOT NULL,
                patronymic TEXT NOT NULL,
                dob TEXT NOT NULL,
                pob TEXT NOT NULL,
                bio TEXT NOT NULL,
                photo_url TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                review_channel_id BIGINT,
                start_roles TEXT
            );
            CREATE TABLE IF NOT EXISTS organizations (
                org_id SERIAL PRIMARY KEY,
                owner_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                org_type TEXT DEFAULT 'Бизнес',
                sphere TEXT DEFAULT 'Не указана',
                level INT DEFAULT 1,
                balance BIGINT DEFAULT 0,
                logo_url TEXT DEFAULT '',
                last_collect DOUBLE PRECISION DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS org_members (
                org_id INT,
                user_id BIGINT,
                rank TEXT DEFAULT 'Сотрудник',
                PRIMARY KEY (org_id, user_id)
            );
            """)

            for statement in (
                "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS state_name TEXT DEFAULT 'РОССИЙСКАЯ ФЕДЕРАЦИЯ';",
                "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS state_name_en TEXT DEFAULT 'RUSSIAN FEDERATION';",
                "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS state_code TEXT DEFAULT 'RUS';",
                "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'RUB';",
                "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS manager_id BIGINT;",
                "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS curator_role BIGINT;",
                "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS mod_role BIGINT;",
                "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS admin_role BIGINT;",
                "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS pr_role BIGINT;",
            ):
                await c.execute(statement)

    async def get_user(self, user_id: int):
        async with self.pool.acquire() as c:
            await c.execute(
                "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id,
            )
            return await c.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)

    async def update_wallet(self, user_id: int, delta: int):
        async with self.pool.acquire() as c:
            await c.execute(
                "UPDATE users SET wallet = GREATEST(wallet + $1, 0) WHERE user_id=$2",
                delta,
                user_id,
            )

    async def set_wallet(self, user_id: int, amount: int):
        async with self.pool.acquire() as c:
            await c.execute(
                "UPDATE users SET wallet = $1 WHERE user_id=$2",
                amount,
                user_id,
            )

    async def log(self, from_id, to_id, amount, kind):
        async with self.pool.acquire() as c:
            await c.execute(
                "INSERT INTO transactions (from_id, to_id, amount, kind) VALUES ($1,$2,$3,$4)",
                from_id,
                to_id,
                amount,
                kind,
            )

    async def get_user_organizations(self, user_id: int):
        """Organizations owned by or joined by the user."""
        async with self.pool.acquire() as c:
            return await c.fetch(
                """
                SELECT DISTINCT o.*
                FROM organizations o
                LEFT JOIN org_members m ON m.org_id = o.org_id AND m.user_id = $1
                WHERE o.owner_id = $1 OR m.user_id IS NOT NULL
                ORDER BY o.org_id
                """,
                user_id,
            )

    async def get_organization(self, org_id: int):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                "SELECT * FROM organizations WHERE org_id=$1",
                org_id,
            )

    async def get_all_organizations(self):
        async with self.pool.acquire() as c:
            return await c.fetch(
                "SELECT * FROM organizations ORDER BY org_id"
            )

    async def create_organization(
        self,
        owner_id: int,
        name: str,
        org_type: str,
        sphere: str,
        logo_url: str,
    ):
        async with self.pool.acquire() as c:
            async with c.transaction():
                org = await c.fetchrow(
                    """
                    INSERT INTO organizations
                        (owner_id, name, org_type, sphere, logo_url, last_collect)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    RETURNING *
                    """,
                    owner_id,
                    name,
                    org_type,
                    sphere,
                    logo_url,
                    __import__("time").time(),
                )
                # The owner is also a normal org member, which makes the
                # member list and permission checks consistent.
                await c.execute(
                    """
                    INSERT INTO org_members (org_id, user_id, rank)
                    VALUES ($1,$2,'Владелец')
                    ON CONFLICT (org_id, user_id)
                    DO UPDATE SET rank='Владелец'
                    """,
                    org["org_id"],
                    owner_id,
                )
                return org

    async def update_organization(
        self,
        org_id: int,
        level: int = None,
        balance: int = None,
        last_collect: float = None,
        name: str = None,
        org_type: str = None,
        sphere: str = None,
        logo_url: str = None,
    ):
        fields = []
        values = []
        for column, value in (
            ("level", level),
            ("balance", balance),
            ("last_collect", last_collect),
            ("name", name),
            ("org_type", org_type),
            ("sphere", sphere),
            ("logo_url", logo_url),
        ):
            if value is not None:
                fields.append(f"{column}=${len(values) + 1}")
                values.append(value)

        if not fields:
            return

        values.append(org_id)
        async with self.pool.acquire() as c:
            await c.execute(
                f"UPDATE organizations SET {', '.join(fields)} WHERE org_id=${len(values)}",
                *values,
            )

    async def add_to_org_balance(self, org_id: int, amount: int):
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE organizations
                SET balance = GREATEST(balance + $1, 0)
                WHERE org_id=$2
                """,
                amount,
                org_id,
            )

    async def delete_organization(self, org_id: int):
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    "DELETE FROM org_members WHERE org_id=$1",
                    org_id,
                )
                await c.execute(
                    "DELETE FROM organizations WHERE org_id=$1",
                    org_id,
                )

    async def get_org_member(self, org_id: int, user_id: int):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                "SELECT * FROM org_members WHERE org_id=$1 AND user_id=$2",
                org_id,
                user_id,
            )

    async def is_org_member(self, org_id: int, user_id: int) -> bool:
        async with self.pool.acquire() as c:
            return bool(
                await c.fetchval(
                    "SELECT 1 FROM org_members WHERE org_id=$1 AND user_id=$2",
                    org_id,
                    user_id,
                )
            )

    async def add_org_member(
        self,
        org_id: int,
        user_id: int,
        rank: str = "Сотрудник",
    ):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                """
                INSERT INTO org_members (org_id, user_id, rank)
                VALUES ($1,$2,$3)
                ON CONFLICT (org_id, user_id)
                DO UPDATE SET rank=EXCLUDED.rank
                RETURNING *
                """,
                org_id,
                user_id,
                rank.strip() or "Сотрудник",
            )

    async def remove_org_member(self, org_id: int, user_id: int):
        async with self.pool.acquire() as c:
            await c.execute(
                "DELETE FROM org_members WHERE org_id=$1 AND user_id=$2",
                org_id,
                user_id,
            )

    async def update_org_member_rank(
        self,
        org_id: int,
        user_id: int,
        rank: str,
    ):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                """
                UPDATE org_members SET rank=$1
                WHERE org_id=$2 AND user_id=$3
                RETURNING *
                """,
                rank.strip() or "Сотрудник",
                org_id,
                user_id,
            )

    async def get_org_members(self, org_id: int):
        async with self.pool.acquire() as c:
            return await c.fetch(
                """
                SELECT * FROM org_members
                WHERE org_id=$1
                ORDER BY
                    CASE WHEN rank='Владелец' THEN 0 ELSE 1 END,
                    user_id
                """,
                org_id,
            )

    async def get_org_member_count(self, org_id: int) -> int:
        async with self.pool.acquire() as c:
            return int(
                await c.fetchval(
                    "SELECT COUNT(*) FROM org_members WHERE org_id=$1",
                    org_id,
                )
                or 0
            )

    async def transfer_organization(self, org_id: int, new_owner_id: int):
        async with self.pool.acquire() as c:
            async with c.transaction():
                old_owner = await c.fetchval(
                    "SELECT owner_id FROM organizations WHERE org_id=$1 FOR UPDATE",
                    org_id,
                )
                if old_owner is None:
                    return False

                await c.execute(
                    "UPDATE organizations SET owner_id=$1 WHERE org_id=$2",
                    new_owner_id,
                    org_id,
                )
                await c.execute(
                    """
                    INSERT INTO org_members (org_id, user_id, rank)
                    VALUES ($1,$2,'Владелец')
                    ON CONFLICT (org_id, user_id)
                    DO UPDATE SET rank='Владелец'
                    """,
                    org_id,
                    new_owner_id,
                )
                if old_owner != new_owner_id:
                    await c.execute(
                        """
                        UPDATE org_members SET rank='Сотрудник'
                        WHERE org_id=$1 AND user_id=$2
                        """,
                        org_id,
                        old_owner,
                    )
                return True

    async def withdraw_org_balance(self, org_id: int, user_id: int, amount: int):
        """Atomically move organization money to a user's wallet."""
        if amount <= 0:
            return False
        async with self.pool.acquire() as c:
            async with c.transaction():
                changed = await c.execute(
                    """
                    UPDATE organizations
                    SET balance=balance-$1
                    WHERE org_id=$2 AND balance >= $1
                    """,
                    amount,
                    org_id,
                )
                if changed != "UPDATE 1":
                    return False
                await c.execute(
                    "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                    user_id,
                )
                await c.execute(
                    "UPDATE users SET wallet=wallet+$1 WHERE user_id=$2",
                    amount,
                    user_id,
                )
                return True

    async def save_passport(self, user_id, surname, name, patronymic, dob, pob, bio, photo_url):
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO passports (user_id, surname, name, patronymic, dob, pob, bio, photo_url)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (user_id) DO UPDATE SET
                    surname=$2, name=$3, patronymic=$4, dob=$5,
                    pob=$6, bio=$7, photo_url=$8
                """,
                user_id,
                surname,
                name,
                patronymic,
                dob,
                pob,
                bio,
                photo_url,
            )

    async def get_passport(self, user_id: int):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                "SELECT * FROM passports WHERE user_id=$1",
                user_id,
            )

    async def update_passport_field(self, user_id: int, field: str, value: str):
        allowed = [
            "surname", "name", "patronymic", "dob",
            "pob", "bio", "photo_url",
        ]
        if field not in allowed:
            return False
        async with self.pool.acquire() as c:
            await c.execute(
                f"UPDATE passports SET {field}=$1 WHERE user_id=$2",
                value,
                user_id,
            )
        return True

    async def set_guild_setting(self, guild_id: int, column: str, value):
        allowed = [
            "review_channel_id", "start_roles", "curator_role", "mod_role",
            "admin_role", "pr_role", "manager_id", "state_name",
            "state_name_en", "state_code", "currency",
        ]
        if column not in allowed:
            return
        async with self.pool.acquire() as c:
            exists = await c.fetchval(
                "SELECT 1 FROM guild_settings WHERE guild_id=$1",
                guild_id,
            )
            if not exists:
                await c.execute(
                    "INSERT INTO guild_settings (guild_id) VALUES ($1)",
                    guild_id,
                )
            await c.execute(
                f"UPDATE guild_settings SET {column}=$1 WHERE guild_id=$2",
                value,
                guild_id,
            )

    async def get_guild_settings(self, guild_id: int):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                "SELECT * FROM guild_settings WHERE guild_id=$1",
                guild_id,
            )
