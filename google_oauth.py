import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle
import email
import base64

from email_utils import load_credentials_from_file
# Scope for read-only access to contacts
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/contacts.other.readonly"
]

def gmail_authenticate():
    creds = None
    # token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If no valid credentials, authenticate user
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('clinet_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save credentials for next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    service = build('gmail', 'v1', credentials=creds)
    return service


def list_messages(service, user_id='me', max_results=10):
    results = service.users().messages().list(userId=user_id, maxResults=max_results).execute()
    messages = results.get('messages', [])
    return messages

def get_message(service, msg_id, user_id='me'):
    msg = service.users().messages().get(userId=user_id, id=msg_id, format='raw').execute()
    msg_str = base64.urlsafe_b64decode(msg['raw'].encode('ASCII')).decode('utf-8')
    mime_msg = email.message_from_string(msg_str)
    return mime_msg