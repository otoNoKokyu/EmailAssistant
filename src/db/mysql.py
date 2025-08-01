from tortoise import Tortoise

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
