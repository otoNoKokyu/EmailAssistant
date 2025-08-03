from tortoise import fields
from tortoise.models import Model
import uuid

class User(Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    email = fields.CharField(max_length=255, unique=True)
    name = fields.CharField(max_length=100, null=True)
    is_verified = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    def __str__(self):
        return self.email
    class Meta:
        table = "users"

    def __str__(self):
        return self.email

    @classmethod
    async def create_user(cls, email: str, name: str = None, is_verified: bool = False):
        return await cls.create(email=email, name=name, is_verified=is_verified)

    @classmethod
    async def get_user_by_id(cls, user_id: uuid.UUID):
        return await cls.get_or_none(id=user_id)

    @classmethod
    async def get_user_by_email(cls, email: str):
        return await cls.get_or_none(email=email)

    async def update_user(self, **kwargs):
        for field, value in kwargs.items():
            setattr(self, field, value)
        await self.save()
        return self

    async def delete_user(self):
        await self.delete()
