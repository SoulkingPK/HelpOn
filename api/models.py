from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class UserCreate(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[EmailStr] = None
    password: str
    get_help: bool = False
    offer_help: bool = False

class UserLogin(BaseModel):
    username: str # Can be email or phone
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    full_name: str = ""

class TokenData(BaseModel):
    username: Optional[str] = None

class UserInDB(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[str] = None
    hashed_password: str
    get_help: bool = False
    offer_help: bool = False
