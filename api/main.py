from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from datetime import timedelta

# Relative imports assuming the current directory is 'api'
# Since Vercel executes from the project root sometimes, we import via absolute paths or local
try:
    from api.models import UserCreate, UserLogin, Token, UserInDB
    from api.database import users_collection
    from api.auth import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
except ImportError:
    from models import UserCreate, UserLogin, Token, UserInDB
    from database import users_collection
    from auth import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

import traceback
from fastapi.responses import JSONResponse

app = FastAPI(title="HelpOn API")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "traceback": traceback.format_exc()}
    )

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to your netlify domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def root():
    return {"message": "HelpOn Backend is running!"}

@app.post("/api/register", response_model=Token)
async def register_user(user: UserCreate):
    if users_collection is None:
        raise HTTPException(
            status_code=500,
            detail="Database connection failed. Please check MONGODB_URL environment variable."
        )

    # Check if user exists by phone or email
    query = {"$or": [{"phone_number": user.phone_number}]}
    if user.email:
        query["$or"].append({"email": user.email})
        
    db_user = await users_collection.find_one(query)
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="User with this phone number or email already exists"
        )
    
    hashed_password = get_password_hash(user.password)
    user_dict = user.dict()
    del user_dict["password"]
    user_dict["hashed_password"] = hashed_password
    
    new_user = await users_collection.insert_one(user_dict)
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.phone_number}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/login", response_model=Token)
async def login_user(login_data: UserLogin):
    if users_collection is None:
        raise HTTPException(
            status_code=500,
            detail="Database connection failed. Please check MONGODB_URL environment variable."
        )

    # Search by email or phone
    user = await users_collection.find_one({
        "$or": [
            {"email": login_data.username},
            {"phone_number": login_data.username}
        ]
    })
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not verify_password(login_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.get("phone_number", user.get("email")))}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
