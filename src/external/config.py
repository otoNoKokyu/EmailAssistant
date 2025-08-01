from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow
import os
CLIENT_SECRET_FILE = "client_secret.json"
import os
import json
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials

class GoogleAuthManager:
    def __init__(
        self,
        client_secret_file: str = "client_secret.json",
        redirect_uri: str = "http://127.0.0.1:8000/oauth2callback",
        scopes: Optional[list] = None,
        token_file: str = "token.json"
    ):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        self.client_secret_file = client_secret_file
        self.redirect_uri = redirect_uri
        self.scopes = scopes or [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/contacts.readonly",
            "https://www.googleapis.com/auth/contacts.other.readonly"
        ]
        self.token_file = token_file
        self._state = None

    def get_login_redirect(self) -> RedirectResponse:
        flow = Flow.from_client_secrets_file(
            self.client_secret_file,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true"
        )
        self._state = state
        return RedirectResponse(auth_url)

    async def handle_callback(self, request: Request) -> Dict[str, Any]:
        if not self._state:
            raise HTTPException(400, "Missing OAuth state. Please retry login.")

        flow = Flow.from_client_secrets_file(
            self.client_secret_file,
            scopes=self.scopes,
            state=self._state,
            redirect_uri=self.redirect_uri
        )
        flow.fetch_token(authorization_response=str(request.url))
        credentials = flow.credentials

        granted = set(credentials.scopes or [])
        required = set(self.scopes)

        if not required.issubset(granted):
            return {
                "status": "partial",
                "missing_scopes": list(required - granted),
                "granted_scopes": list(granted),
                "requested_scopes": list(required)
            }

        self._save_credentials(credentials)
        return {
            "status": "success",
            "granted_scopes": list(granted),
            "message": "Authenticated successfully"
        }

    def _save_credentials(self, credentials: Credentials):
        data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes
        }
        with open(self.token_file, "w") as f:
            json.dump(data, f)

    def load_credentials(self) -> Optional[Credentials]:
        if not os.path.exists(self.token_file):
            return None
        with open(self.token_file) as f:
            data = json.load(f)
        creds = Credentials(
            token=data["token"],
            refresh_token=data.get("refresh_token"),
            token_uri=data["token_uri"],
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            scopes=data["scopes"]
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        return creds

