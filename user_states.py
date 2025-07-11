from enum import Enum
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
import json

class UserState(Enum):
    """User interaction states"""
    IDLE = "idle"
    ADDING_COLLECTION_NAME = "adding_collection_name"
    ADDING_STICKERPACK_NAME = "adding_stickerpack_name"
    ADDING_LAUNCH_PRICE = "adding_launch_price"
    CONFIRMING_COLLECTION = "confirming_collection"
    EDITING_COLLECTION = "editing_collection"
    EDITING_BUY_MULTIPLIER = "editing_buy_multiplier"
    EDITING_SELL_MULTIPLIER = "editing_sell_multiplier"

@dataclass
class CollectionData:
    """Temporary collection data during creation/editing"""
    collection_name: Optional[str] = None
    stickerpack_name: Optional[str] = None
    launch_price: Optional[float] = None
    editing_collection_id: Optional[str] = None

@dataclass
class UserSessionData:
    """User session data"""
    state: UserState = UserState.IDLE
    collection_data: CollectionData = field(default_factory=CollectionData)
    last_message_id: Optional[int] = None
    
    def reset(self):
        """Reset user session to idle state"""
        self.state = UserState.IDLE
        self.collection_data = CollectionData()
        self.last_message_id = None

class UserStateManager:
    """Manages user states and temporary data"""
    
    def __init__(self):
        self.user_sessions: Dict[int, UserSessionData] = {}
        
    def get_user_session(self, user_id: int) -> UserSessionData:
        """Get or create user session"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = UserSessionData()
        return self.user_sessions[user_id]
    
    def set_user_state(self, user_id: int, state: UserState):
        """Set user state"""
        session = self.get_user_session(user_id)
        session.state = state
    
    def get_user_state(self, user_id: int) -> UserState:
        """Get user state"""
        session = self.get_user_session(user_id)
        return session.state
    
    def is_user_in_flow(self, user_id: int) -> bool:
        """Check if user is in an active flow"""
        return self.get_user_state(user_id) != UserState.IDLE
    
    def reset_user_session(self, user_id: int):
        """Reset user session to idle"""
        if user_id in self.user_sessions:
            self.user_sessions[user_id].reset()
    
    def update_collection_data(self, user_id: int, **kwargs):
        """Update collection data for user"""
        session = self.get_user_session(user_id)
        for key, value in kwargs.items():
            if hasattr(session.collection_data, key):
                setattr(session.collection_data, key, value)
    
    def get_collection_data(self, user_id: int) -> CollectionData:
        """Get collection data for user"""
        session = self.get_user_session(user_id)
        return session.collection_data
    
    def set_last_message_id(self, user_id: int, message_id: int):
        """Set last message ID for user"""
        session = self.get_user_session(user_id)
        session.last_message_id = message_id
    
    def get_last_message_id(self, user_id: int) -> Optional[int]:
        """Get last message ID for user"""
        session = self.get_user_session(user_id)
        return session.last_message_id 