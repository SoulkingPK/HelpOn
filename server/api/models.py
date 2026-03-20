from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
import re

def sanitize_string(v: str) -> str:
    """Basic XSS prevention by stripping HTML tags."""
    if not isinstance(v, str):
        return v
    return re.sub(r'<[^>]*?>', '', v).strip()

class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    phone_number: str = Field(..., min_length=10, max_length=15)
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=8)
    get_help: bool = False
    offer_help: bool = False

    @validator("full_name", pre=True)
    def sanitize_name(cls, v):
        return sanitize_string(v)

class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=100) # Can be email or phone
    password: str = Field(..., min_length=1)

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    full_name: str = ""

class TokenData(BaseModel):
    username: Optional[str] = None

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class UserInDB(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[str] = None
    hashed_password: str
    get_help: bool = False
    offer_help: bool = False
    is_admin: bool = False
    
# --- New Models for Real-World Features --- #

class LocationUpdate(BaseModel):
    lat: float
    lon: float

class UserLocationResponse(BaseModel):
    id: str
    full_name: str
    lat: float
    lon: float
    last_updated: str
    verified: bool = False
    kyc_status: str = "none"

class EmergencyCreate(BaseModel):
    type: str = Field(..., min_length=2, max_length=50)
    description: str = Field(..., min_length=5, max_length=500)
    lat: float
    lon: float

    @validator("type", "description", pre=True)
    def sanitize_emergency_fields(cls, v):
        return sanitize_string(v)

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
    email: Optional[str] = None
    phone_number: str
    avatar: Optional[str] = None
    points: int
    helps_given: int
    local_rank: int
    verified: bool
    kyc_status: str = "none" # "none", "pending", "approved", "rejected"
    is_admin: bool = False

class UserSettingsUpdate(BaseModel):
    notifications_enabled: bool
    privacy_mode: bool

class UserProfileUpdate(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone_number: str
    avatar: Optional[str] = None

# --- Rewards & Redemptions Models --- #

class RewardResponse(BaseModel):
    id: str
    name: str
    description: str
    points_cost: int
    image_text: str
    image_color: str

class RedemptionResponse(BaseModel):
    id: str
    reward_id: str
    reward_name: str
    voucher_code: str
    status: str
    created_at: str

# --- Support & Help Models --- #

class HelpRequestCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=10, max_length=2000)

    @validator("name", "subject", "message", pre=True)
    def sanitize_support_fields(cls, v):
        return sanitize_string(v)

class HelpRequestResponse(BaseModel):
    id: str
    name: str
    subject: str
    status: str
    created_at: str
    user_id: Optional[str] = None


# --- KYC Models --- #

class KYCSubmission(BaseModel):
    document_type: str = Field(..., min_length=2, max_length=50) # e.g., "Aadhar", "PAN", "Driver License"
    document_number: str = Field(..., min_length=4, max_length=50)
    document_image_url: str = Field(..., min_length=10)

    @validator("document_type", "document_number", pre=True)
    def sanitize_kyc_fields(cls, v):
        return sanitize_string(v)

class KYCResponse(BaseModel):
    id: str
    user_id: str
    document_type: str
    document_number: str
    document_image_url: str
    status: str # "pending", "approved", "rejected"
    admin_feedback: Optional[str] = None
    created_at: str
    verified_at: Optional[str] = None
