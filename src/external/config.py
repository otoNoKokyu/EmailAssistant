from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow
import os

from src.models.googleCredential import GoogleCredential
from src.models.user import User
CLIENT_SECRET_FILE = "client_secret.json"
import os
from google.oauth2 import id_token as google_id_token
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials

from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from datetime import datetime
import uuid

class GoogleAuthManager:
    def __init__(
        self,
        client_secret_file: str = "client_secret.json",
        redirect_uri: str = "http://127.0.0.1:8000/oauth2callback",
        scopes: Optional[list] = None,
    ):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        self.client_secret_file = client_secret_file
        self.redirect_uri = redirect_uri
        self.scopes = scopes or [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/contacts.readonly",
            "https://www.googleapis.com/auth/contacts.other.readonly",
            "openid",
            "https://www.googleapis.com/auth/userinfo.email"
        ]
        self._state_cache = {}

    def get_login_redirect(self, session_id: str) -> RedirectResponse:
        flow = Flow.from_client_secrets_file(
            self.client_secret_file,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"  # force refresh_token even on repeat
        )
        self._state_cache[session_id] = state
        return RedirectResponse(auth_url)



    async def handle_callback(self, request: Request, session_id: str) -> Dict[str, Any]:
        try:
            # Validate state
            state = self._state_cache.get(session_id)
            if not state:
                raise HTTPException(400, "Missing OAuth state. Please retry login.")

            # Build and fetch token from Google
            flow = Flow.from_client_secrets_file(
                self.client_secret_file,
                scopes=self.scopes,
                state=state,
                redirect_uri=self.redirect_uri
            )

            try:
                flow.fetch_token(authorization_response=str(request.url))
            except Exception as e:
                raise HTTPException(400, f"Failed to fetch token: {e}")

            creds = flow.credentials

            try:
                id_info = google_id_token.verify_oauth2_token(
                    creds.id_token,
                    GoogleRequest(),
                    creds.client_id
                )
                user_email = id_info.get("email")
                user_id = id_info.get("sub")
            except Exception:
                raise HTTPException(400, "Failed to decode ID token.")

            if not user_email:
                raise HTTPException(400, "Email not available in ID token.")

            # Create or get user
            user = await User.get_or_none(email=user_email)
            if not user:
                user = await User.create(email=user_email, name=None, is_verified=True)

            # Save credentials in DB
            try:
                await GoogleCredential.update_or_create(
                    defaults={
                        "token": creds.token,
                        "refresh_token": creds.refresh_token,
                        "token_uri": creds.token_uri,
                        "client_id": creds.client_id,
                        "client_secret": creds.client_secret,
                        "scopes": creds.scopes,
                        "expiry": creds.expiry,
                    },
                    user=user,
                    gmail_account_email=user_email,
                )
            except e:
                raise HTTPException(500, f"Failed to save credentials: {e}")

            # Scope validation
            granted, required = set(creds.scopes or []), set(self.scopes)
            if not required.issubset(granted):
                return {
                    "status": "partial",
                    "missing_scopes": list(required - granted),
                    "granted_scopes": list(granted),
                    "requested_scopes": list(required)
                }

            return {
                "status": "success",
                "granted_scopes": list(granted),
                "email": user_email,
                "message": "Authenticated and credentials saved"
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Unexpected error: {e}")

    async def load_credentials(self, user: User, gmail_account_email: str) -> Optional[Credentials]:
        cred = await GoogleCredential.get_or_none(user=user, gmail_account_email=gmail_account_email)
        if not cred:
            return None

        creds = Credentials(
            token=cred.token,
            refresh_token=cred.refresh_token,
            token_uri=cred.token_uri,
            client_id=cred.client_id,
            client_secret=cred.client_secret,
            scopes=cred.scopes
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            # Update DB with new values
            cred.token = creds.token
            cred.expiry = creds.expiry
            await cred.save()

        return creds
