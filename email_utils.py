import smtplib
import os
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
from email.mime.text import MIMEText
from dotenv import load_dotenv
from googleapiclient.discovery import build


load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


def get_gmail_service():
    creds = load_credentials_from_file()
    if not creds:
        return "User not authenticated. Please visit /login first."
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
    service = build('gmail', 'v1', credentials=creds)
    return service

import smtplib
from email.mime.text import MIMEText


def send_email(to_email, subject, body):

    creds = load_credentials_from_file()
    service =  build('people', 'v1', credentials=creds)
    recipient = find_contact(service,to_email)
    print(recipient)

    try:
        msg = MIMEText(body)
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = recipient
        msg["Subject"] = subject

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)

        print(f"Email sent to {to_email}")

    except Exception as e:
        print(f"[ERROR] Failed to send email to {to_email}: {e}")

def reply_email(original_message_id, to_email, subject, body):
    creds = load_credentials_from_file()
    service = build('people', 'v1', credentials=creds)
    recipient = find_contact(service, to_email)
    print(f"Replying to: {recipient}")

    try:
        msg = MIMEText(body)
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = recipient
        msg["Subject"] = subject
        
        msg["In-Reply-To"] = original_message_id
        msg["References"] = original_message_id



        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)

        print(f"Reply sent to {to_email} | Thread ID: {original_message_id}")

    except Exception as e:
        print(f"[ERROR] Reply failed to {to_email}: {str(e)}")



import base64
import re

def search_emails(query: str, max_results: int):
    try:
        service = get_gmail_service()
        response = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()
        
        messages_data = response.get('messages', [])
        messages = []
        
        for msg in messages_data:
            try:
                msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                headers = {h['name'].lower(): h['value'] for h in msg_data['payload'].get('headers', [])}
                
                # Extract body
                def extract_body(payload):
                    if 'parts' in payload:
                        for part in payload['parts']:
                            mime = part.get('mimeType')
                            data = part.get('body', {}).get('data')
                            if mime == 'text/plain' and data:
                                return base64.urlsafe_b64decode(data).decode('utf-8').strip()
                            elif mime == 'text/html' and data:
                                html = base64.urlsafe_b64decode(data).decode('utf-8')
                                return re.sub('<[^<]+?>', '', html).strip()
                            elif 'parts' in part:
                                return extract_body(part)
                    else:
                        data = payload.get('body', {}).get('data')
                        if payload.get('mimeType') == 'text/plain' and data:
                            return base64.urlsafe_b64decode(data).decode('utf-8').strip()
                    return ''
                
                # Check attachments
                def has_attachments(payload):
                    for part in payload.get('parts', []):
                        if part.get('filename'):
                            return True
                        if 'parts' in part and has_attachments(part):
                            return True
                    return False
                
                # Extract reply-specific header
                message_id = headers.get('message-id', '')
                
                messages.append({
                    "id": msg['id'],
                    "subject": headers.get('subject', 'No Subject'),
                    "from": headers.get('from', 'Unknown'),
                    "to": headers.get('to', 'Unknown'),
                    "date": headers.get('date'),
                    "snippet": msg_data.get('snippet', ''),
                    "labels": msg_data.get('labelIds', []),
                    "message_id": message_id,  # Only reply attribute needed
                })
                
            except Exception as e:
                print(f"Error in message {msg['id']}: {e}")
                continue
        
        return {
            "status": "success",
            "query": query,
            "results": messages,
            "found": len(messages) > 0
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e), "query": query}
def send_reply(to_email, subject, body, reply_to_message_id):
    """Send a reply to an existing email"""
    creds = load_credentials_from_file()
    service = build('people', 'v1', credentials=creds)
    recipient = find_contact(service, to_email)
    
    try:
        msg = MIMEText(body)
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email
        msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re: ") else subject
        msg["In-Reply-To"] = reply_to_message_id
        msg["References"] = reply_to_message_id
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"Reply sent to {to_email}")
        
    except Exception as e:
        print(f"[ERROR] Failed to send reply to {to_email}: {e}")


def get_full_message_body(payload):
    """Extracts the full body text from the message payload."""
    import base64

    def decode_body(body):
        data = body.get('data')
        if data:
            return base64.urlsafe_b64decode(data.encode('UTF-8')).decode('utf-8', errors='replace')
        return ""

    if payload.get('body', {}).get('data'):
        return decode_body(payload['body'])

    # If multipart, look for the plain text part
    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            if mime_type == 'text/plain':
                return decode_body(part['body'])
        # Fallback to HTML if plain text not found
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            if mime_type == 'text/html':
                return decode_body(part['body'])
    return ""

def save_credentials_to_file(credentials, filename='token.json'):
    import json
    data = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    with open(filename, 'w') as f:
        json.dump(data, f)

def load_credentials_from_file(filename='token.json'):
    import os
    import json
    from google.oauth2.credentials import Credentials

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
    return creds


import re

def find_contact(service, q):
    """
    Search for contacts from Google People API 'otherContacts'
    that match the query in either name or email.

    Args:
        service: Authorized People API service instance.
        q (str): Regex or plain search query string.

    Returns:
        List of dicts: [{'name': ..., 'email': ...}, ...]
    """
    try:
        print("Fetching contacts...")
        results = service.otherContacts().list(
            pageSize=1000,
            readMask='names,emailAddresses'
        ).execute()

        connections = results.get('otherContacts', [])

        contacts = []
        for person in connections:
            names = person.get('names', [])
            emails = person.get('emailAddresses', [])
            if emails:
                contact = {
                    'name': names[0].get('displayName') if names else '',
                    'email': emails[0].get('value')
                }
                contacts.append(contact)

        print(f"Total valid contacts: {len(contacts)}")
        contacts.append({'name':'me','email': 'arko466@gmail.com'})

        # Search
        pattern = re.compile( re.sub(r"^\{\{(.*?)\}\}$", r"\1", q), re.IGNORECASE)
        matched = [
            contact for contact in contacts
            if pattern.search(contact['name']) or pattern.search(contact['email'])
        ]
        print(f"Matched: {len(matched)}")
        return matched[0]['email']

    except Exception as e:
        print(f"[ERROR] Failed to fetch or filter contacts: {e}")
        return []
