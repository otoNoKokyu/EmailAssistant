import os
import json
from dotenv import load_dotenv
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


load_dotenv()

from abc import ABC, abstractmethod

class EmailProvider(ABC):
    @abstractmethod
    def get_email_address(self) -> str:
        pass

    @abstractmethod
    def get_email_password(self) -> str:
        pass

    @abstractmethod
    def get_mail_client(self):  # could be Gmail, Outlook, etc.
        pass

    @abstractmethod
    def get_contact_client(self):  # e.g. Google People API, Outlook People API
        pass

    @abstractmethod
    def find_contact_email(self, query: str) -> str:
        """
        Find and return an email address matching a contact search query.
        """
        pass


class GmailProvider(EmailProvider):
    def __init__(self):
        self._email = os.getenv("EMAIL_ADDRESS")
        self._password = os.getenv("EMAIL_PASSWORD")

    def get_email_address(self) -> str:
        return self._email

    def get_email_password(self) -> str:
        return self._password

    def _load_credentials(self, filename='token.json'):
        if not os.path.exists(filename):
            return None
        with open(filename, 'r') as f:
            data = json.load(f)
        creds = Credentials(
            token=data['token'],
            refresh_token=data.get('refresh_token'),
            token_uri=data['token_uri'],
            client_id=data['client_id'],
            client_secret=data['client_secret'],
            scopes=data['scopes']
        )
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        return creds

    def get_mail_client(self):
        return build("gmail", "v1", credentials=self._load_credentials())

    def get_contact_client(self):
        return build("people", "v1", credentials=self._load_credentials())

    def find_contact_email(self, query: str) -> str:
        service = self.get_contact_client()
        results = service.otherContacts().list(
            pageSize=1000,
            readMask='names,emailAddresses'
        ).execute()

        contacts = results.get("otherContacts", [])
        contacts.append({"name": "me", "email": self._email})

        pattern = re.compile(query, re.IGNORECASE)

        for person in contacts:
            names = person.get("names", [])
            emails = person.get("emailAddresses", [])
            if not emails:
                continue
            email = emails[0]["value"]
            name = names[0]["displayName"] if names else ""
            if pattern.search(name) or pattern.search(email):
                return email

        return query  # fallback