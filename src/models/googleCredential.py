from tortoise import fields
from tortoise.models import Model
import uuid


class GoogleCredential(Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    user = fields.ForeignKeyField("models.User", related_name="google_credentials")
    gmail_account_email = fields.CharField(max_length=255)  # e.g. johndoe@gmail.com
    token = fields.TextField()
    refresh_token = fields.TextField(null=True)
    token_uri = fields.TextField()
    client_id = fields.TextField()
    client_secret = fields.TextField()
    scopes = fields.JSONField()
    expiry = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "google_credentials"
