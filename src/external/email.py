import os
from dotenv import load_dotenv
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build



from abc import ABC, abstractmethod

from src.models.googleCredential import GoogleCredential

class EmailProvider(ABC):
    @abstractmethod
    def get_email_address(self) -> str:
        pass

    @abstractmethod
    def get_email_password(self) -> str:
        pass

    @abstractmethod
    async def get_mail_client(self):  # could be Gmail, Outlook, etc.
        pass

    @abstractmethod
    async def get_contact_client(self):  # e.g. Google People API, Outlook People API
        pass



class GmailProvider(EmailProvider):
    def __init__(self, credential_record: GoogleCredential):
        """
        credential_record: GoogleCredential instance from DB
        """
        load_dotenv()
        self.cred_record = credential_record
        self._email = credential_record.gmail_account_email

    def get_email_address(self) -> str:
        return self._email

    def get_email_password(self) -> str:
        return os.getenv("EMAIL_PASSWORD")

    async def _load_credentials(self):
        creds = Credentials(
            token=self.cred_record.token,
            refresh_token=self.cred_record.refresh_token,
            token_uri=self.cred_record.token_uri,
            client_id=self.cred_record.client_id,
            client_secret=self.cred_record.client_secret,
            scopes=self.cred_record.scopes,
        )

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            # Update DB with new token and expiry
            self.cred_record.token = creds.token
            self.cred_record.expiry = creds.expiry
            await self.cred_record.save()

        return creds

    async def get_mail_client(self):
        creds = await self._load_credentials()
        if not creds or not creds.valid:
            raise Exception("Invalid Gmail credentials. Please re-authenticate.")
        return build("gmail", "v1", credentials=creds)

    async def get_contact_client(self):
        creds = await self._load_credentials()
        if not creds or not creds.valid:
            raise Exception("Invalid Gmail credentials. Please re-authenticate.")
        return build("people", "v1", credentials=creds)
