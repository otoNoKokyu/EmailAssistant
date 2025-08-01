import smtplib
from email.mime.text import MIMEText
import base64
import re

from typing import List, Dict
from external.email import EmailProvider


class EmailAssistant:
    def __init__(self, provider: EmailProvider):
        self.provider = provider
        self.email = provider.get_email_address()
        self.password = provider.get_email_password()

    def send_email(self, to_email: str, subject: str, body: str):
        recipient = self.provider.find_contact_email(to_email)

        msg = MIMEText(body)
        msg["From"] = self.email
        msg["To"] = recipient
        msg["Subject"] = subject

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:  # Optional: abstract SMTP host too
            smtp.login(self.email, self.password)
            smtp.send_message(msg)

    def send_reply(self, to_email: str, subject: str, body: str, reply_to_message_id: str):
        recipient = self.provider.find_contact_email(to_email)

        msg = MIMEText(body)
        msg["From"] = self.email
        msg["To"] = recipient
        msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re: ") else subject
        msg["In-Reply-To"] = reply_to_message_id
        msg["References"] = reply_to_message_id

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(self.email, self.password)
            smtp.send_message(msg)

    def search_emails(self, query: str, max_results: int = 10) -> Dict:
        try:
            gmail_client = self.provider.get_mail_client()
            response = gmail_client.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()

            messages_data = response.get("messages", [])
            messages = []

            for msg in messages_data:
                msg_data = gmail_client.users().messages().get(
                    userId="me", id=msg["id"], format="full"
                ).execute()

                headers = {
                    h["name"].lower(): h["value"]
                    for h in msg_data["payload"].get("headers", [])
                }

                message_id = headers.get("message-id", "")

                messages.append({
                    "id": msg["id"],
                    "subject": headers.get("subject", "No Subject"),
                    "from": headers.get("from", "Unknown"),
                    "to": headers.get("to", "Unknown"),
                    "date": headers.get("date"),
                    "snippet": msg_data.get("snippet", ""),
                    "labels": msg_data.get("labelIds", []),
                    "message_id": message_id,
                })

            return {
                "status": "success",
                "query": query,
                "results": messages,
                "found": len(messages) > 0
            }

        except Exception as e:
            return {
                "status": "error",
                "query": query,
                "error": str(e),
            }

    def get_full_message_body(self, payload: Dict) -> str:
        def decode_body(body):
            data = body.get("data")
            if data:
                return base64.urlsafe_b64decode(data.encode("UTF-8")).decode("utf-8", errors="replace")
            return ""

        if payload.get("body", {}).get("data"):
            return decode_body(payload["body"])

        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    return decode_body(part["body"])
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html":
                    html = decode_body(part["body"])
                    return re.sub("<[^<]+?>", "", html).strip()

        return ""
