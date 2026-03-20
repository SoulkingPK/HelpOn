from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from typing import Optional, List
from fastapi import WebSocket, WebSocketDisconnect

from .auth import verify_token
from .database import users_collection

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login", auto_error=False)

async def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme)):
    # Try header first, then cookie
    if not token:
        token = request.cookies.get("helpon_access_token")
        
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    user = await users_collection.find_one({
        "$or": [{"email": username}, {"phone_number": username}]
    })
    
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_current_user_optional(request: Request, token: Optional[str] = Depends(oauth2_scheme)):
    if not token:
        token = request.cookies.get("helpon_access_token")
        
    if not token:
        return None
    try:
        user = await get_current_user(request, token)
        return user
    except:
        return None

async def require_admin(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires admin privileges"
        )
    return current_user

class ConnectionManager:
    """
    Manages WebSocket connections. 
    In production with multiple instances, this should be replaced by 
    Redis Pub/Sub or a similar message broker.
    """
    def __init__(self):
        # Maps user_id strings to sets of WebSocket objects
        self.active_connections: dict[str, set[WebSocket]] = {}
        # For non-authenticated or broad broadcasts
        self.anonymous_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, user_id: str = None):
        await websocket.accept()
        if user_id:
            if user_id not in self.active_connections:
                self.active_connections[user_id] = set()
            self.active_connections[user_id].add(websocket)
        else:
            self.anonymous_connections.add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: str = None):
        if user_id and user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        else:
            self.anonymous_connections.discard(websocket)

    async def send_personal_message(self, message: dict, user_id: str):
        """Send a message to all sessions of a specific user."""
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    async def broadcast(self, message: dict):
        """Broadcast a message to everyone."""
        # Broadcast to authenticated users
        for user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass
        
        # Broadcast to anonymous users
        for connection in self.anonymous_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)

# Basic CSRF Protection (Double Submit Cookie Pattern)
async def verify_csrf(request: Request):
    if request.method in ["GET", "HEAD", "OPTIONS", "TRACE"]:
        return
    
    csrf_cookie = request.cookies.get("helpon_csrf_token")
    csrf_header = request.headers.get("X-CSRF-Token")
    
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token validation failed"
        )
