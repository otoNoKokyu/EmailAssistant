from contextlib import asynccontextmanager
import json
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from googleapiclient.discovery import build

@asynccontextmanager
async def lifespan(app: FastAPI):
    shared_state["initialized"] = True
    print("🌟 App initializing…")
    await init_expensive_resources()
    yield
    # Code during shutdown
    await cleanup_resources()
    print("🧹 Cleanup complete")

app = FastAPI(lifespan=lifespan)



app = FastAPI()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/contacts.other.readonly"
]
REDIRECT_URI = "http://127.0.0.1:8000/oauth2callback"
def get_people_service():
    creds = load_credentials_from_file()

    """Get authenticated People API service."""
    flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
    return build('people', 'v1', credentials=creds)


user_credentials = {}
def search_contacts(service, query):
    """Search contacts by name/email."""
    try:
        results = service.people().searchContacts(
            query=query,
            readMask='names,emailAddresses'
        ).execute()
        
        contacts = []
        for result in results.get('results', []):
            person = result.get('person', {})
            name = person.get('names', [{}])[0].get('displayName', 'No Name')
            email = person.get('emailAddresses', [{}])[0].get('value', 'No Email')
            contacts.append({'name': name, 'email': email})
        
        return results
    except Exception as e:
        print(f"Error: {e}")
        return []

@app.get("/login")
def login():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    # Save the state somewhere (e.g., session). Here just in-memory for demo.
    user_credentials['state'] = state
    return RedirectResponse(authorization_url)




from fastapi import Request, HTTPException

@app.get("/oauth2callback")
async def oauth2callback(request: Request):
    state = user_credentials.get('state')
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state. Please retry login.")

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI
    )
    authorization_response = str(request.url)

    flow.fetch_token(authorization_response=authorization_response)


    credentials = flow.credentials

    # Check granted scopes vs requested scopes
    granted_scopes = set(credentials.scopes or [])
    requested_scopes = set(SCOPES)

    if not requested_scopes.issubset(granted_scopes):
        # Some requested scopes were not granted
        missing = requested_scopes - granted_scopes
        return {
            "status": "Partial authentication",
            "message": f"Warning: The following scopes were not granted: {', '.join(missing)}",
            "granted_scopes": list(granted_scopes),
            "requested_scopes": list(requested_scopes)
        }

    # Store credentials and granted scopes (in-memory here)
    user_credentials['credentials'] = credentials
    user_credentials['granted_scopes'] = list(granted_scopes)
    save_credentials_to_file(credentials)

    return {
        "status": "Authentication successful",
        "message": "You can now call /google-contacts",
        "granted_scopes": list(granted_scopes)
    }


def get_email_body(payload):
    """Extract email body and preprocess it"""
    body = ""
    
    # Check if the message is multipart
    if 'parts' in payload:
        for part in payload['parts']:
            # Look for text parts
            if 'body' in part and 'data' in part['body']:
                body = part['body']['data']
                return preprocess_email_body(body)
            
            # Check for nested parts
            if 'parts' in part:
                for subpart in part['parts']:
                    if 'body' in subpart and 'data' in subpart['body']:
                        body = subpart['body']['data']
                        return preprocess_email_body(body)
    
    # If not multipart
    elif 'body' in payload and 'data' in payload['body']:
        body = payload['body']['data']
        return preprocess_email_body(body)
            
    return body

def get_gmail_service():
    creds = load_credentials_from_file()
    if not creds:
        raise HTTPException(status_code=401, detail="User not authenticated. Please visit /login first.")
    # Refresh token if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
    service = build('gmail', 'v1', credentials=creds)
    return service

@app.get("/search")
def search_messages(query: str = Query(...)):
    # service = get_gmail_service()
    # p = handle_user_queries(query)
    # return p
    response_str  = Invoke_LLM(query)
    # return response_str
    try:
        return {'data':do_agentic_shit(response_str["actions"],query),'actions':response_str['actions']}
        actions = response_str["actions"]
        for action in actions:
            process_action(action)
        return response_str
    except json.JSONDecodeError as e:
        print("Failed to parse LLM response as JSON:", e)
    