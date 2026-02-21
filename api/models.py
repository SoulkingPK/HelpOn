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
    
# --- New Models for Real-World Features --- #

class LocationUpdate(BaseModel):
    lat: float
    lon: float

class EmergencyCreate(BaseModel):
    type: str
    description: str
    lat: float
    lon: float

class EmergencyResponse(BaseModel):
    id: str
    type: str
    description: str
    lat: float
    lon: float
    created_by: str
    status: str
    created_at: str
    helper_id: Optional[str] = None

class NotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    is_read: bool
    created_at: str
    type: str

class UserProfileResponse(BaseModel):
    full_name: str
    points: int
    helps_given: int
    local_rank: int
    verified: bool

class UserSettingsUpdate(BaseModel):
    notifications_enabled: bool
    privacy_mode: bool
