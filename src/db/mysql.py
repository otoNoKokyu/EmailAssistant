from dotenv import load_dotenv
from tortoise import Tortoise
import os

load_dotenv()

TORTOISE_ORM = {
   "connections": {
        "default": {
            "engine": "tortoise.backends.mysql",
            "credentials": {
                "host": os.getenv("DB_HOST"),
                "port": os.getenv("DB_PORT", 3306),
                "user": os.getenv("DB_USERNAME"),
                "password": os.getenv("DB_PASSWORD"),
                "database": os.getenv("DB_DATABASE"),
                "charset": "utf8mb4",
                "sql_mode": "STRICT_TRANS_TABLES",
                "connect_timeout": 60,
                "pool_recycle": 3600,
                "minsize": 1,
                "maxsize": 10,
            }
        },
    },
    "apps": {
        "models": {
            "models": ["src.models.user","src.models.googleCredential"], 
            "default_connection": "default",
        },
    },
}
class Database:
    def __init__(self, db_url: str, modules: dict, pool_min_size: int = 1, pool_max_size: int = 10):
        self.db_url = db_url
        self.modules = modules
        self.pool_min_size = pool_min_size
        self.pool_max_size = pool_max_size

    async def connect(self, generate_schemas=True):
        await Tortoise.init(
            db_url=self.db_url,
            modules=self.modules,
            _create_db=False,
            pool_minsize=self.pool_min_size,
            pool_maxsize=self.pool_max_size,
            pool_recycle=3600,
        )
        if generate_schemas:
            await Tortoise.generate_schemas()

    async def disconnect(self):
        await Tortoise.close_connections()
