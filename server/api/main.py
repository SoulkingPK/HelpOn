from fastapi import FastAPI, HTTPException, status, Depends
from typing import Optional, List, Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from datetime import timedelta

import sys
import os
import cloudinary
import cloudinary.uploader

# Add the 'server' directory to sys.path so Vercel can resolve 'api.models'
# __file__ is server/api/main.py, so we need the parent of the parent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import using absolute paths corresponding to the injected sys.path
from api.models import (
    UserCreate, UserLogin, Token, UserInDB, LocationUpdate,
    EmergencyCreate, EmergencyResponse, NotificationResponse,
    UserProfileResponse, UserSettingsUpdate, UserProfileUpdate,
    HelpRequestCreate, HelpRequestResponse, ChatbotQuery, RefreshTokenRequest,
    RewardResponse, RedemptionResponse, UserLocationResponse
)
from api.database import (
    users_collection, emergencies_collection, notifications_collection,
    support_requests_collection, faqs_collection, rewards_collection, user_redemptions_collection
)
from api.auth import get_password_hash, verify_password, create_access_token, create_refresh_token, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, verify_token, verify_refresh_token

import traceback
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime
from bson import ObjectId
from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict

from api.dependencies import get_current_user, get_current_user_optional, manager, limiter

app = FastAPI(title="HelpOn API")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the full error internally if a logging system is available
    # For now, we print to stderr or use a placeholder for a logging service
    print(f"ERROR: {exc}")
    
    # Hide traceback in production to prevent information leakage
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please contact support if the problem persists."}
    )

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://soulkingpk.github.io",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.on_event("startup")
async def startup_db_client():
    if users_collection is not None:
        try:
            await users_collection.create_index([("last_location", "2dsphere")])
        except Exception:
            pass
    if emergencies_collection is not None:
        try:
            await emergencies_collection.create_index([("location", "2dsphere")])
        except Exception:
            pass

@app.get("/api/health")
async def root():
    return {"message": "HelpOn Backend is running!"}

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Can be used to handle incoming messages like "ping" to keep connection alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

from api.routes.auth import router as auth_router
from api.routes.users import router as users_router
from api.routes.emergencies import router as emergencies_router
from api.routes.support import router as support_router
from api.routes.rewards import router as rewards_router
from api.routes.admin import router as admin_router
from api.routes.kyc import router as kyc_router

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api/users")
app.include_router(emergencies_router, prefix="/api/emergency")
app.include_router(support_router, prefix="/api")
app.include_router(rewards_router, prefix="/api")
app.include_router(admin_router, prefix="/api/admin")
app.include_router(kyc_router, prefix="/api/kyc")
