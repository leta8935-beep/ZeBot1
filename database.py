
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()


class Database:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.getenv("DATABASE_URL")
        self.pool = None

    async def connect(self):
        if self.pool:
            return
        if not self.dsn:
            raise RuntimeError("DATABASE_URL не задан.")
        self.pool = await asyncpg.create_pool(
            self.dsn, min_size=1, max_size=8,
            statement_cache_size=0, max_cached_statement_lifetime=0
        )
        await self._create_schema()

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def _create_schema(self):
        async with self.pool.acquire() as c:
            await c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                wallet BIGINT NOT NULL DEFAULT 500,
                bank BIGINT NOT NULL DEFAULT 0,
                job TEXT,
                level INT NOT NULL DEFAULT 1,
                xp BIGINT NOT NULL DEFAULT 0,
                last_daily DOUBLE PRECISION NOT NULL DEFAULT 0,
                last_work DOUBLE PRECISION NOT NULL DEFAULT 0,
                last_xp DOUBLE PRECISION NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            ALTER TABLE users ADD COLUMN IF NOT EXISTS bank BIGINT NOT NULL DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS job TEXT;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS level INT NOT NULL DEFAULT 1;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS xp BIGINT NOT NULL DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily DOUBLE PRECISION NOT NULL DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS last_work DOUBLE PRECISION NOT NULL DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS last_xp DOUBLE PRECISION NOT NULL DEFAULT 0;

            CREATE TABLE IF NOT EXISTS transactions (
                id BIGSERIAL PRIMARY KEY,
                from_id BIGINT, to_id BIGINT, amount BIGINT NOT NULL,
                kind TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS passports (
                user_id BIGINT PRIMARY KEY, surname TEXT NOT NULL, name TEXT NOT NULL,
                patronymic TEXT NOT NULL, dob TEXT NOT NULL, pob TEXT NOT NULL,
                bio TEXT NOT NULL, photo_url TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                review_channel_id BIGINT,
                start_roles TEXT,
                state_name TEXT DEFAULT 'РОССИЙСКАЯ ФЕДЕРАЦИЯ',
                state_name_en TEXT DEFAULT 'RUSSIAN FEDERATION',
                state_code TEXT DEFAULT 'RUS',
                currency TEXT DEFAULT 'RUB',
                manager_id BIGINT,
                curator_role BIGINT,
                mod_role BIGINT,
                admin_role BIGINT,
                pr_role BIGINT,
                welcome_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                welcome_channel_id BIGINT
            );
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS review_channel_id BIGINT;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS start_roles TEXT;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS state_name TEXT DEFAULT 'РОССИЙСКАЯ ФЕДЕРАЦИЯ';
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS state_name_en TEXT DEFAULT 'RUSSIAN FEDERATION';
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS state_code TEXT DEFAULT 'RUS';
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'RUB';
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS manager_id BIGINT;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS curator_role BIGINT;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS mod_role BIGINT;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS admin_role BIGINT;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS pr_role BIGINT;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS welcome_enabled BOOLEAN NOT NULL DEFAULT FALSE;
            ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS welcome_channel_id BIGINT;

            CREATE TABLE IF NOT EXISTS shop_items (
                item_id BIGSERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                description TEXT, price BIGINT NOT NULL, role_id BIGINT
            );
            CREATE TABLE IF NOT EXISTS inventory (
                user_id BIGINT, item_id BIGINT REFERENCES shop_items(item_id) ON DELETE CASCADE,
                quantity BIGINT NOT NULL DEFAULT 1, PRIMARY KEY (user_id, item_id)
            );
            CREATE TABLE IF NOT EXISTS market (
                listing_id BIGSERIAL PRIMARY KEY, seller_id BIGINT NOT NULL,
                item_id BIGINT REFERENCES shop_items(item_id) ON DELETE CASCADE,
                quantity BIGINT NOT NULL, price BIGINT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS parties (
                party_id BIGSERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                ideology TEXT DEFAULT 'Не указана', description TEXT DEFAULT '—',
                slogan TEXT DEFAULT '—', color TEXT DEFAULT '#1e3a8a',
                flag_file TEXT, flag_mode TEXT DEFAULT 'flag',
                leader_id BIGINT, treasury BIGINT DEFAULT 0, created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS party_members (
                user_id BIGINT, party_id BIGINT REFERENCES parties(party_id) ON DELETE CASCADE,
                role TEXT DEFAULT 'member', joined_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (user_id, party_id)
            );

            CREATE TABLE IF NOT EXISTS elections (
                election_id BIGSERIAL PRIMARY KEY, type TEXT NOT NULL, title TEXT NOT NULL,
                date_text TEXT DEFAULT '—', turnout INT DEFAULT 75, total_seats INT DEFAULT 200,
                channel_id BIGINT, status TEXT DEFAULT 'draft', created_by BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW(), posted_at TIMESTAMPTZ
            );
            CREATE TABLE IF NOT EXISTS election_candidates (
                candidate_id BIGSERIAL PRIMARY KEY, election_id BIGINT REFERENCES elections(election_id) ON DELETE CASCADE,
                user_id BIGINT, party_id BIGINT, display_name TEXT NOT NULL,
                ideology TEXT DEFAULT '—', party_name TEXT DEFAULT '—', color TEXT DEFAULT '#1e3a8a',
                photo_file TEXT, flag_file TEXT, flag_mode TEXT DEFAULT 'flag',
                votes DOUBLE PRECISION DEFAULT 0, seats INT DEFAULT 0, order_idx INT DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS organizations (
                org_id BIGSERIAL PRIMARY KEY,
                owner_id BIGINT,
                name TEXT UNIQUE NOT NULL,
                org_type TEXT DEFAULT 'Бизнес',
                sphere TEXT DEFAULT 'Не указана',
                level INT DEFAULT 1,
                balance BIGINT DEFAULT 0,
                logo_url TEXT DEFAULT '',
                last_collect DOUBLE PRECISION DEFAULT 0,
                short_name TEXT,
                type TEXT DEFAULT 'government',
                category TEXT DEFAULT 'organization',
                description TEXT DEFAULT '—',
                motto TEXT DEFAULT '—',
                color TEXT DEFAULT '#1e3a8a',
                logo_file TEXT,
                logo_mode TEXT DEFAULT 'emblem',
                leader_id BIGINT,
                budget BIGINT DEFAULT 0,
                salary BIGINT DEFAULT 0,
                is_open BOOLEAN DEFAULT TRUE,
                created_by BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS owner_id BIGINT;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS org_type TEXT DEFAULT 'Бизнес';
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS sphere TEXT DEFAULT 'Не указана';
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS level INT DEFAULT 1;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS balance BIGINT DEFAULT 0;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS logo_url TEXT DEFAULT '';
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS last_collect DOUBLE PRECISION DEFAULT 0;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS short_name TEXT;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'government';
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'organization';
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '—';
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS motto TEXT DEFAULT '—';
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS color TEXT DEFAULT '#1e3a8a';
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS logo_file TEXT;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS logo_mode TEXT DEFAULT 'emblem';
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS leader_id BIGINT;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS budget BIGINT DEFAULT 0;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS salary BIGINT DEFAULT 0;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS is_open BOOLEAN DEFAULT TRUE;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS created_by BIGINT;
            ALTER TABLE organizations ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

            CREATE TABLE IF NOT EXISTS organization_members (
                user_id BIGINT, org_id BIGINT REFERENCES organizations(org_id) ON DELETE CASCADE,
                role TEXT DEFAULT 'member', salary BIGINT DEFAULT 0, joined_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (user_id, org_id)
            );
            CREATE TABLE IF NOT EXISTS organization_requests (
                request_id BIGSERIAL PRIMARY KEY,
                org_id BIGINT REFERENCES organizations(org_id) ON DELETE CASCADE, user_id BIGINT,
                message TEXT DEFAULT '—', status TEXT DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE (org_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS organization_history (
                id BIGSERIAL PRIMARY KEY,
                org_id BIGINT REFERENCES organizations(org_id) ON DELETE CASCADE,
                kind TEXT, amount BIGINT DEFAULT 0, user_id BIGINT, comment TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS tuppers (
                tupper_id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, name TEXT NOT NULL,
                avatar_url TEXT, created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(user_id, name)
            );
            CREATE TABLE IF NOT EXISTS tupper_sessions (
                user_id BIGINT PRIMARY KEY, tupper_id BIGINT NOT NULL, channel_id BIGINT NOT NULL,
                webhook_id BIGINT, webhook_token TEXT, enabled BOOLEAN DEFAULT TRUE
            );
            """)

            # Мягкая миграция организаций из старой версии ZeBot.
            await c.execute("""
                UPDATE organizations
                SET leader_id = COALESCE(leader_id, owner_id),
                    created_by = COALESCE(created_by, owner_id),
                    budget = COALESCE(NULLIF(budget, 0), COALESCE(balance, 0)),
                    description = COALESCE(NULLIF(description, ''), '—'),
                    motto = COALESCE(NULLIF(motto, ''), '—')
                WHERE leader_id IS NULL OR created_by IS NULL
            """)
            await c.execute("""
                INSERT INTO organization_members (user_id, org_id, role)
                SELECT o.leader_id, o.org_id, 'leader'
                FROM organizations o
                WHERE o.leader_id IS NOT NULL
                ON CONFLICT (user_id, org_id) DO UPDATE SET role='leader'
            """)
            # Дефолтный магазин.
            count = await c.fetchval("SELECT COUNT(*) FROM shop_items")
            if count == 0:
                await c.executemany(
                    "INSERT INTO shop_items (name, description, price) VALUES ($1,$2,$3)",
                    [
                        ("Рыболовная удочка", "Позволяет рыбачить. +шанс на улов", 1500),
                        ("Кирка", "Для добычи руды в шахтах", 2000),
                        ("Автомобиль", "Престижный транспорт RP-жителя", 25000),
                        ("Особняк", "Элитная недвижимость", 150000),
                        ("Лицензия на оружие", "Разрешение на ношение", 10000),
                        ("VIP-статус", "Особый статус в государстве", 50000),
                    ],
                )

    async def get_user(self, user_id):
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
            return await c.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)

    async def update_user(self, user_id, **fields):
        if not fields: return
        allowed = {"wallet","bank","job","level","xp","last_daily","last_work","last_xp"}
        fields = {k:v for k,v in fields.items() if k in allowed}
        if not fields: return
        cols = ", ".join(f"{k}=${i+1}" for i,k in enumerate(fields))
        vals = list(fields.values()) + [user_id]
        async with self.pool.acquire() as c:
            await c.execute(f"UPDATE users SET {cols} WHERE user_id=${len(vals)}", *vals)

    async def add_balance(self, user_id, amount, to_bank=False):
        field = "bank" if to_bank else "wallet"
        async with self.pool.acquire() as c:
            await c.execute(f"UPDATE users SET {field}={field}+$1 WHERE user_id=$2", amount, user_id)

    async def update_wallet(self, user_id, delta):
        await self.add_balance(user_id, delta, False)

    async def set_wallet(self, user_id, amount):
        await self.update_user(user_id, wallet=amount)

    async def log_transaction(self, from_id, to_id, amount, kind):
        async with self.pool.acquire() as c:
            await c.execute(
                "INSERT INTO transactions (from_id,to_id,amount,kind) VALUES ($1,$2,$3,$4)",
                from_id,to_id,amount,kind
            )

    async def log(self, from_id, to_id, amount, kind):
        await self.log_transaction(from_id,to_id,amount,kind)

    async def all_users(self):
        async with self.pool.acquire() as c:
            return await c.fetch("SELECT * FROM users ORDER BY user_id")

    async def top_richest(self, limit=10):
        async with self.pool.acquire() as c:
            return await c.fetch("SELECT user_id, wallet+bank AS total FROM users ORDER BY total DESC LIMIT $1", limit)

    async def top_level(self, limit=10):
        async with self.pool.acquire() as c:
            return await c.fetch("SELECT user_id, level, xp FROM users ORDER BY level DESC, xp DESC LIMIT $1", limit)

    async def shop_list(self):
        async with self.pool.acquire() as c:
            return await c.fetch("SELECT * FROM shop_items ORDER BY price")

    async def get_item(self, name):
        async with self.pool.acquire() as c:
            return await c.fetchrow("SELECT * FROM shop_items WHERE LOWER(name)=LOWER($1)", name)

    async def get_item_by_id(self, item_id):
        async with self.pool.acquire() as c:
            return await c.fetchrow("SELECT * FROM shop_items WHERE item_id=$1", item_id)

    async def add_item_to_inventory(self, user_id, item_id, qty=1):
        async with self.pool.acquire() as c:
            await c.execute("""
                INSERT INTO inventory(user_id,item_id,quantity) VALUES($1,$2,$3)
                ON CONFLICT(user_id,item_id) DO UPDATE SET quantity=inventory.quantity+EXCLUDED.quantity
            """, user_id,item_id,qty)

    async def remove_item_from_inventory(self, user_id, item_id, qty=1):
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT quantity FROM inventory WHERE user_id=$1 AND item_id=$2", user_id,item_id)
            if not row or row["quantity"] < qty: return False
            if row["quantity"] == qty:
                await c.execute("DELETE FROM inventory WHERE user_id=$1 AND item_id=$2", user_id,item_id)
            else:
                await c.execute("UPDATE inventory SET quantity=quantity-$1 WHERE user_id=$2 AND item_id=$3", qty,user_id,item_id)
            return True

    async def clear_inventory(self, user_id):
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM inventory WHERE user_id=$1", user_id)

    async def get_inventory(self, user_id):
        async with self.pool.acquire() as c:
            return await c.fetch("""
                SELECT s.name,s.item_id,i.quantity FROM inventory i
                JOIN shop_items s ON s.item_id=i.item_id WHERE i.user_id=$1
            """, user_id)

    async def create_listing(self, seller_id,item_id,qty,price):
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO market(seller_id,item_id,quantity,price) VALUES($1,$2,$3,$4)",seller_id,item_id,qty,price)

    async def market_listings(self):
        async with self.pool.acquire() as c:
            return await c.fetch("""
                SELECT m.listing_id,m.seller_id,m.quantity,m.price,s.name,s.item_id
                FROM market m JOIN shop_items s ON s.item_id=m.item_id ORDER BY m.created_at DESC
            """)

    async def get_listing(self, listing_id):
        async with self.pool.acquire() as c:
            return await c.fetchrow("SELECT * FROM market WHERE listing_id=$1", listing_id)

    async def delete_listing(self, listing_id):
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM market WHERE listing_id=$1", listing_id)

    async def create_party(self,name,leader_id,ideology,color,description):
        async with self.pool.acquire() as c:
            async with c.transaction():
                row=await c.fetchrow(
                    "INSERT INTO parties(name,leader_id,ideology,color,description) VALUES($1,$2,$3,$4,$5) RETURNING party_id",
                    name,leader_id,ideology,color,description
                )
                pid=row["party_id"]
                await c.execute("INSERT INTO party_members(user_id,party_id,role) VALUES($1,$2,'leader') ON CONFLICT DO NOTHING",leader_id,pid)
                return pid

    async def get_party(self,identifier):
        async with self.pool.acquire() as c:
            if isinstance(identifier,int):
                return await c.fetchrow("SELECT * FROM parties WHERE party_id=$1",identifier)
            return await c.fetchrow("SELECT * FROM parties WHERE LOWER(name)=LOWER($1)",identifier)

    async def all_parties(self):
        async with self.pool.acquire() as c:
            return await c.fetch("SELECT * FROM parties ORDER BY treasury DESC,name")

    async def update_party(self,party_id,**fields):
        if not fields:return
        allowed={"name","ideology","description","slogan","color","flag_file","flag_mode","leader_id","treasury"}
        fields={k:v for k,v in fields.items() if k in allowed}
        if not fields:return
        cols=", ".join(f"{k}=${i+1}" for i,k in enumerate(fields))
        vals=list(fields.values())+[party_id]
        async with self.pool.acquire() as c:
            await c.execute(f"UPDATE parties SET {cols} WHERE party_id=${len(vals)}",*vals)

    async def delete_party(self,party_id):
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM parties WHERE party_id=$1",party_id)

    async def add_party_member(self,user_id,party_id,role="member"):
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO party_members(user_id,party_id,role) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",user_id,party_id,role)

    async def remove_party_member(self,user_id,party_id):
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM party_members WHERE user_id=$1 AND party_id=$2",user_id,party_id)

    async def get_user_party(self,user_id):
        async with self.pool.acquire() as c:
            return await c.fetchrow("""SELECT p.*,pm.role FROM party_members pm JOIN parties p ON p.party_id=pm.party_id WHERE pm.user_id=$1""",user_id)

    async def get_party_members(self,party_id):
        async with self.pool.acquire() as c:
            return await c.fetch("SELECT user_id,role FROM party_members WHERE party_id=$1 ORDER BY role DESC",party_id)

    async def add_party_treasury(self,party_id,amount):
        async with self.pool.acquire() as c:
            await c.execute("UPDATE parties SET treasury=treasury+$1 WHERE party_id=$2",amount,party_id)

    async def create_election(self,type_,title,channel_id,created_by):
        async with self.pool.acquire() as c:
            row=await c.fetchrow("INSERT INTO elections(type,title,channel_id,created_by) VALUES($1,$2,$3,$4) RETURNING election_id",type_,title,channel_id,created_by)
            return row["election_id"]

    async def get_election(self,eid):
        async with self.pool.acquire() as c:return await c.fetchrow("SELECT * FROM elections WHERE election_id=$1",eid)

    async def update_election(self,eid,**fields):
        if not fields:return
        allowed={"type","title","date_text","turnout","total_seats","channel_id","status","created_by","posted_at"}
        fields={k:v for k,v in fields.items() if k in allowed}
        if not fields:return
        cols=", ".join(f"{k}=${i+1}" for i,k in enumerate(fields))
        vals=list(fields.values())+[eid]
        async with self.pool.acquire() as c:await c.execute(f"UPDATE elections SET {cols} WHERE election_id=${len(vals)}",*vals)

    async def delete_election(self,eid):
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM elections WHERE election_id=$1",eid)

    async def all_elections(self):
        async with self.pool.acquire() as c:return await c.fetch("SELECT * FROM elections ORDER BY election_id DESC LIMIT 15")

    async def add_candidate(self,eid,**fields):
        allowed={"user_id","party_id","display_name","ideology","party_name","color","photo_file","flag_file","flag_mode","votes","seats","order_idx"}
        fields={k:v for k,v in fields.items() if k in allowed}
        cols=", ".join(fields.keys()); vals=list(fields.values())
        placeholders=", ".join(f"${i+1}" for i in range(len(vals)+1))
        async with self.pool.acquire() as c:
            row=await c.fetchrow(f"INSERT INTO election_candidates(election_id,{cols}) VALUES($1,{', '.join(f'${i+2}' for i in range(len(vals)))}) RETURNING candidate_id",eid,*vals)
            return row["candidate_id"]

    async def get_candidates(self,eid):
        async with self.pool.acquire() as c:return await c.fetch("SELECT * FROM election_candidates WHERE election_id=$1 ORDER BY order_idx,candidate_id",eid)

    async def update_candidate(self,cid,**fields):
        allowed={"user_id","party_id","display_name","ideology","party_name","color","photo_file","flag_file","flag_mode","votes","seats","order_idx"}
        fields={k:v for k,v in fields.items() if k in allowed}
        if not fields:return
        cols=", ".join(f"{k}=${i+1}" for i,k in enumerate(fields)); vals=list(fields.values())+[cid]
        async with self.pool.acquire() as c:await c.execute(f"UPDATE election_candidates SET {cols} WHERE candidate_id=${len(vals)}",*vals)

    async def delete_candidate(self,cid):
        async with self.pool.acquire() as c:await c.execute("DELETE FROM election_candidates WHERE candidate_id=$1",cid)

    async def create_org(self,name,leader_id,type_,category,description,motto,color,short_name,created_by):
        async with self.pool.acquire() as c:
            async with c.transaction():
                row=await c.fetchrow("""
                    INSERT INTO organizations(name,short_name,type,category,description,motto,color,leader_id,created_by,owner_id)
                    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$8) RETURNING org_id
                """,name,short_name,type_,category,description,motto,color,leader_id,created_by)
                oid=row["org_id"]
                await c.execute("INSERT INTO organization_members(user_id,org_id,role) VALUES($1,$2,'leader') ON CONFLICT DO NOTHING",leader_id,oid)
                await c.execute("INSERT INTO organization_history(org_id,kind,user_id,comment) VALUES($1,'create',$2,'Организация создана')",oid,created_by)
                return oid

    async def create_organization(self,owner_id,name,org_type,sphere,logo_url):
        # Совместимость со старой регистрацией: заявка/одобрение создаёт новую организацию.
        type_ = "government" if str(org_type).lower() in ("государственная","government","гос") else "private"
        category = "company" if str(org_type).lower() in ("бизнес","business","компания","private") else "organization"
        return await self.create_org(name,owner_id,type_,category,f"Сфера: {sphere}","—","#1e3a8a",None,owner_id)

    async def get_org(self,identifier):
        async with self.pool.acquire() as c:
            if isinstance(identifier,int):
                return await c.fetchrow("SELECT * FROM organizations WHERE org_id=$1",identifier)
            return await c.fetchrow("""SELECT * FROM organizations WHERE LOWER(name)=LOWER($1) OR LOWER(short_name)=LOWER($1)""",identifier)

    async def all_orgs(self,category=None,type_=None):
        q="SELECT * FROM organizations"; cond=[]; vals=[]
        if category: cond.append(f"category=${len(vals)+1}"); vals.append(category)
        if type_: cond.append(f"type=${len(vals)+1}"); vals.append(type_)
        if cond:q+=" WHERE "+" AND ".join(cond)
        q+=" ORDER BY budget DESC,name"
        async with self.pool.acquire() as c:return await c.fetch(q,*vals)

    async def update_org(self,org_id,**fields):
        allowed={"name","short_name","type","category","description","motto","color","logo_file","logo_mode","leader_id","budget","salary","is_open","created_by","owner_id","org_type","sphere","level","balance","logo_url","last_collect"}
        fields={k:v for k,v in fields.items() if k in allowed}
        if not fields:return
        cols=", ".join(f"{k}=${i+1}" for i,k in enumerate(fields)); vals=list(fields.values())+[org_id]
        async with self.pool.acquire() as c:await c.execute(f"UPDATE organizations SET {cols} WHERE org_id=${len(vals)}",*vals)

    async def delete_org(self,org_id):
        async with self.pool.acquire() as c:await c.execute("DELETE FROM organizations WHERE org_id=$1",org_id)

    async def add_org_member(self,user_id,org_id,role="member",salary=0):
        async with self.pool.acquire() as c:
            await c.execute("""INSERT INTO organization_members(user_id,org_id,role,salary) VALUES($1,$2,$3,$4)
                               ON CONFLICT(user_id,org_id) DO UPDATE SET role=EXCLUDED.role,salary=EXCLUDED.salary""",user_id,org_id,role,salary)

    async def remove_org_member(self,user_id,org_id):
        async with self.pool.acquire() as c:await c.execute("DELETE FROM organization_members WHERE user_id=$1 AND org_id=$2",user_id,org_id)

    async def get_user_org(self,user_id):
        async with self.pool.acquire() as c:return await c.fetchrow("""SELECT o.*,m.role,m.salary FROM organization_members m JOIN organizations o ON o.org_id=m.org_id WHERE m.user_id=$1""",user_id)

    async def get_org_members(self,org_id):
        async with self.pool.acquire() as c:return await c.fetch("""SELECT user_id,role,salary FROM organization_members WHERE org_id=$1 ORDER BY CASE role WHEN 'leader' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END,joined_at""",org_id)

    async def count_org_members(self,org_id):
        async with self.pool.acquire() as c:return await c.fetchval("SELECT COUNT(*) FROM organization_members WHERE org_id=$1",org_id)

    async def update_org_member(self,user_id,org_id,**fields):
        allowed={"role","salary"}
        fields={k:v for k,v in fields.items() if k in allowed}
        if not fields:return
        cols=", ".join(f"{k}=${i+1}" for i,k in enumerate(fields)); vals=list(fields.values())+[user_id,org_id]
        async with self.pool.acquire() as c:await c.execute(f"UPDATE organization_members SET {cols} WHERE user_id=${len(vals)-1} AND org_id=${len(vals)}",*vals)

    async def add_org_budget(self,org_id,amount,kind="adjust",user_id=None,comment=None):
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute("UPDATE organizations SET budget=budget+$1 WHERE org_id=$2",amount,org_id)
                await c.execute("INSERT INTO organization_history(org_id,kind,amount,user_id,comment) VALUES($1,$2,$3,$4,$5)",org_id,kind,amount,user_id,comment)

    async def get_org_history(self,org_id,limit=15):
        async with self.pool.acquire() as c:return await c.fetch("SELECT * FROM organization_history WHERE org_id=$1 ORDER BY id DESC LIMIT $2",org_id,limit)

    async def create_org_request(self,org_id,user_id,message):
        async with self.pool.acquire() as c:
            await c.execute("""INSERT INTO organization_requests(org_id,user_id,message,status) VALUES($1,$2,$3,'pending')
                               ON CONFLICT(org_id,user_id) DO UPDATE SET message=EXCLUDED.message,status='pending',created_at=NOW()""",org_id,user_id,message)

    async def get_org_request(self,req_id):
        async with self.pool.acquire() as c:return await c.fetchrow("SELECT * FROM organization_requests WHERE request_id=$1",req_id)

    async def get_org_requests(self,org_id,status="pending"):
        async with self.pool.acquire() as c:return await c.fetch("SELECT * FROM organization_requests WHERE org_id=$1 AND status=$2 ORDER BY created_at",org_id,status)

    async def get_user_org_request(self,user_id,org_id):
        async with self.pool.acquire() as c:return await c.fetchrow("SELECT * FROM organization_requests WHERE user_id=$1 AND org_id=$2 AND status='pending'",user_id,org_id)

    async def set_org_request_status(self,req_id,status):
        async with self.pool.acquire() as c:await c.execute("UPDATE organization_requests SET status=$1 WHERE request_id=$2",status,req_id)

    async def get_tupper(self,tupper_id):
        async with self.pool.acquire() as c:return await c.fetchrow("SELECT * FROM tuppers WHERE tupper_id=$1",tupper_id)

    async def get_tupper_by_name(self,user_id,name):
        async with self.pool.acquire() as c:return await c.fetchrow("SELECT * FROM tuppers WHERE user_id=$1 AND LOWER(name)=LOWER($2)",user_id,name)

    async def list_tuppers(self,user_id):
        async with self.pool.acquire() as c:return await c.fetch("SELECT * FROM tuppers WHERE user_id=$1 ORDER BY name",user_id)

    async def create_tupper(self,user_id,name,avatar_url=None):
        try:
            async with self.pool.acquire() as c:
                row=await c.fetchrow("INSERT INTO tuppers(user_id,name,avatar_url) VALUES($1,$2,$3) RETURNING tupper_id",user_id,name,avatar_url)
                return row["tupper_id"]
        except Exception:return None

    async def delete_tupper(self,tupper_id):
        async with self.pool.acquire() as c:await c.execute("DELETE FROM tuppers WHERE tupper_id=$1",tupper_id)

    async def update_tupper(self,tupper_id,**fields):
        allowed={"name","avatar_url"}; fields={k:v for k,v in fields.items() if k in allowed}
        if not fields:return
        cols=", ".join(f"{k}=${i+1}" for i,k in enumerate(fields)); vals=list(fields.values())+[tupper_id]
        async with self.pool.acquire() as c:await c.execute(f"UPDATE tuppers SET {cols} WHERE tupper_id=${len(vals)}",*vals)

    async def get_tupper_session(self,user_id):
        async with self.pool.acquire() as c:return await c.fetchrow("SELECT * FROM tupper_sessions WHERE user_id=$1",user_id)

    async def set_tupper_session(self,user_id,tupper_id,channel_id,webhook_id=None,webhook_token=None):
        async with self.pool.acquire() as c:
            await c.execute("""INSERT INTO tupper_sessions(user_id,tupper_id,channel_id,webhook_id,webhook_token,enabled)
                               VALUES($1,$2,$3,$4,$5,TRUE)
                               ON CONFLICT(user_id) DO UPDATE SET tupper_id=EXCLUDED.tupper_id,channel_id=EXCLUDED.channel_id,
                               webhook_id=EXCLUDED.webhook_id,webhook_token=EXCLUDED.webhook_token,enabled=TRUE""",
                           user_id,tupper_id,channel_id,webhook_id,webhook_token)

    async def update_tupper_session_webhook(self,user_id,webhook_id,webhook_token):
        async with self.pool.acquire() as c:await c.execute("UPDATE tupper_sessions SET webhook_id=$1,webhook_token=$2 WHERE user_id=$3",webhook_id,webhook_token,user_id)

    async def disable_tupper_session(self,user_id):
        async with self.pool.acquire() as c:await c.execute("UPDATE tupper_sessions SET enabled=FALSE WHERE user_id=$1",user_id)

    async def enable_tupper_session(self,user_id):
        async with self.pool.acquire() as c:await c.execute("UPDATE tupper_sessions SET enabled=TRUE WHERE user_id=$1",user_id)

    async def get_passport(self,user_id):
        async with self.pool.acquire() as c:return await c.fetchrow("SELECT * FROM passports WHERE user_id=$1",user_id)

    async def save_passport(self,user_id,surname,name,patronymic,dob,pob,bio,photo_url):
        async with self.pool.acquire() as c:
            await c.execute("""INSERT INTO passports(user_id,surname,name,patronymic,dob,pob,bio,photo_url)
                               VALUES($1,$2,$3,$4,$5,$6,$7,$8)
                               ON CONFLICT(user_id) DO UPDATE SET surname=$2,name=$3,patronymic=$4,dob=$5,pob=$6,bio=$7,photo_url=$8""",
                           user_id,surname,name,patronymic,dob,pob,bio,photo_url)

    async def update_passport_field(self,user_id,field,value):
        allowed={"surname","name","patronymic","dob","pob","bio","photo_url"}
        if field not in allowed:return False
        async with self.pool.acquire() as c:await c.execute(f"UPDATE passports SET {field}=$1 WHERE user_id=$2",value,user_id)
        return True

    async def set_guild_setting(self,guild_id,column,value):
        allowed={"review_channel_id","start_roles","curator_role","mod_role","admin_role","pr_role","manager_id",
                 "state_name","state_name_en","state_code","currency","welcome_enabled","welcome_channel_id"}
        if column not in allowed:return
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO guild_settings(guild_id) VALUES($1) ON CONFLICT DO NOTHING",guild_id)
            await c.execute(f"UPDATE guild_settings SET {column}=$1 WHERE guild_id=$2",value,guild_id)

    async def get_guild_settings(self,guild_id):
        async with self.pool.acquire() as c:return await c.fetchrow("SELECT * FROM guild_settings WHERE guild_id=$1",guild_id)

    async def add_shop_item(self, name, description, price, role_id=None):
        async with self.pool.acquire() as c:
            await c.execute("INSERT INTO shop_items(name,description,price,role_id) VALUES($1,$2,$3,$4)",
                            name,description,price,role_id)

    async def delete_shop_item(self, item_id):
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM shop_items WHERE item_id=$1", item_id)

    async def transaction_report(self):
        async with self.pool.acquire() as c:
            return await c.fetch(
                "SELECT kind, COUNT(*) AS c, COALESCE(SUM(amount),0) AS total "
                "FROM transactions GROUP BY kind ORDER BY total DESC"
            )



db = Database()
