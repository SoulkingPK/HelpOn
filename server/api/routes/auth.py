from fastapi import APIRouter, HTTPException, Depends, Request, Response, status
import secrets
from datetime import timedelta
from typing import Optional

from ..auth import (
    get_password_hash, verify_password, create_access_token, 
    create_refresh_token, verify_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
)
from ..models import UserCreate, UserLogin
from ..database import users_collection
from ..dependencies import limiter

router = APIRouter(tags=["Auth"])

@router.post("/register")
@limiter.limit("5/hour")
async def register_user(user: UserCreate, request: Request, response: Response):
    if users_collection is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    existing_user = await users_collection.find_one({
        "$or": [{"email": user.email}, {"phone_number": user.phone_number}]
    })
    
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email or phone number already exists")
        
    hashed_password = get_password_hash(user.password)
    
    user_dict = {
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "email": user.email,
        "hashed_password": hashed_password,
        "get_help": user.get_help,
        "offer_help": user.offer_help,
        "points": 0,
        "helps_given": 0,
        "verified": False,
        "is_admin": False,
        "last_ip": request.client.host if request.client else request.headers.get("x-forwarded-for", "Unknown"),
        "last_ua": request.headers.get("user-agent", "Unknown")
    }
    
    result = await users_collection.insert_one(user_dict)
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.phone_number or user.email)}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.phone_number or user.email)}, expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    
    # Set HTTP-only cookies
    response.set_cookie(
        key="helpon_access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="helpon_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    
    # Set CSRF cookie (NOT HttpOnly so JS can read it)
    csrf_token = secrets.token_hex(32)
    response.set_cookie(
        key="helpon_csrf_token",
        value=csrf_token,
        httponly=False,
        secure=True, 
        samesite="none",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    
    return {"status": "User registered successfully", "id": str(result.inserted_id), "full_name": user.full_name}

@router.post("/login")
@limiter.limit("10/minute")
async def login_user(login_data: UserLogin, request: Request, response: Response):
    user = await users_collection.find_one({
        "$or": [{"email": login_data.username}, {"phone_number": login_data.username}]
    })
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
    if not verify_password(login_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.get("phone_number", user.get("email")))}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.get("phone_number", user.get("email")))},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    
    # Set cookies
    response.set_cookie(
        key="helpon_access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="helpon_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

    # Set CSRF cookie
    csrf_token = secrets.token_hex(32)
    response.set_cookie(
        key="helpon_csrf_token",
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="none",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    
    # Update last login info
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "last_ip": request.client.host if request.client else request.headers.get("x-forwarded-for", "Unknown"),
            "last_ua": request.headers.get("user-agent", "Unknown"),
            "last_active": datetime.utcnow()
        }}
    )
    
    return {"token_type": "bearer", "full_name": str(user.get("full_name", ""))}

@router.post("/refresh")
async def refresh_access_token(request: Request, response: Response):
    ref_token = request.cookies.get("helpon_refresh_token")
    if not ref_token:
        try:
            body = await request.json()
            ref_token = body.get("refresh_token")
        except:
            pass
            
    if not ref_token:
        raise HTTPException(status_code=400, detail="No refresh token provided")

    payload = verify_refresh_token(ref_token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await users_collection.find_one({
        "$or": [{"email": username}, {"phone_number": username}]
    })
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.get("phone_number", user.get("email")))}, expires_delta=access_token_expires
    )
    new_refresh_token = create_refresh_token(
        data={"sub": str(user.get("phone_number", user.get("email")))},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    response.set_cookie(
        key="helpon_access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="helpon_refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

    # Set CSRF cookie
    csrf_token = secrets.token_hex(32)
    response.set_cookie(
        key="helpon_csrf_token",
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="none",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

    return {
        "token_type": "bearer",
        "full_name": str(user.get("full_name", ""))
    }
    
@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="helpon_access_token", secure=True, httponly=True, samesite="none")
    response.delete_cookie(key="helpon_refresh_token", secure=True, httponly=True, samesite="none")
    return {"status": "Logged out successfully"}
