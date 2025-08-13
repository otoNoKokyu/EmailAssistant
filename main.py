from contextlib import asynccontextmanager
import json
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from googleapiclient.discovery import build
from tortoise import Tortoise
from tortoise.contrib.fastapi import register_tortoise
from src.models.googleCredential import GoogleCredential
from src.service.emailService import EmailAssistant
from src.service.llmService import  EmailAgentOrchestrator, EmailAgent
from src.models.user import User
from src.db.mysql import TORTOISE_ORM
from fastapi.middleware.cors import CORSMiddleware
from src.external.config import GoogleAuthManager


@asynccontextmanager
async def tortoise_app_context(app):
    await Tortoise.init(TORTOISE_ORM)
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()

app = FastAPI(lifespan=tortoise_app_context)
origins = [
    "http://localhost:5173",  
    "http://127.0.0.1:5173", 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          
    allow_credentials=True,
    allow_methods=["*"],            
    allow_headers=["*"],            
)
auth_manager = GoogleAuthManager()
llmAgent = EmailAgentOrchestrator()


@app.get("/hasUsers")
async def has_users():
    user_exists = await User.exists()
    return {"has_users": user_exists}

@app.get("/login")
def login(request: Request):
    session_id = request.client.host
    return auth_manager.get_login_redirect(session_id)



@app.get("/oauth2callback")
async def oauth2callback(request: Request):
    session_id = request.client.host  

    try:
        result = await auth_manager.handle_callback(request, session_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth failed: {str(e)}")

    if result["status"] == "partial":
        return JSONResponse(
            status_code=206,
            content={
                "status": "Partial authentication",
                "message": result["message"],
                "missing_scopes": result["missing_scopes"],
                "granted_scopes": result["granted_scopes"],
                "requested_scopes": result["requested_scopes"]
            }
        )

    return {
        "status": "Authentication successful",
        "message": "You can now call Gmail or Contacts APIs.",
        "email": result["email"],
        "granted_scopes": result["granted_scopes"]
    }


@app.get("/search")
async def search_messages(query: str = Query(...),email: str = Query(None)):
    try:
        userCredential = await GoogleCredential.get_or_none(gmail_account_email=email)
        if not userCredential:
            return JSONResponse(status_code=409, content={"status": "error", "message": "User credentials not found."})
        emailProvider = EmailAssistant(credential_record=userCredential)
        emailAgent = EmailAgent(emailProvider, llmAgent,query)
        actions = llmAgent.getEmailActions(query)
        x = await emailAgent.run(actions)
        return JSONResponse(status_code=200, content={"status": "success", "data": x})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    except json.JSONDecodeError as e:
        print("Failed to parse LLM response as JSON:", e)
    