import json
import hashlib
import hmac
import time
import urllib.parse
from typing import Dict, List, Optional, Any
import aiohttp
import logging

from config import (
    AUTH_ENDPOINT, PRICE_BUNDLES_ENDPOINT,
    TELEGRAM_INIT_DATA, TELEGRAM_USER_ID, TELEGRAM_FIRST_NAME, TELEGRAM_LAST_NAME,
    TELEGRAM_USERNAME, TELEGRAM_LANGUAGE_CODE, TELEGRAM_IS_PREMIUM,
    TELEGRAM_PHOTO_URL
)

logger = logging.getLogger(__name__)

class Scanner:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.access_token: Optional[str] = None
        self.user_data: Optional[Dict] = None
        self.token_expires_at: Optional[int] = None
        
    def _generate_init_data(self) -> str:
        """Generate Telegram WebApp initData string"""
        # Create user data object
        user_data = {
            "id": int(TELEGRAM_USER_ID),
            "first_name": TELEGRAM_FIRST_NAME,
            "last_name": TELEGRAM_LAST_NAME,
            "username": TELEGRAM_USERNAME,
            "language_code": TELEGRAM_LANGUAGE_CODE,
            "is_premium": TELEGRAM_IS_PREMIUM,
            "allows_write_to_pm": True
        }
        
        if TELEGRAM_PHOTO_URL:
            user_data["photo_url"] = TELEGRAM_PHOTO_URL
            
        # URL encode the user data
        user_encoded = urllib.parse.quote(json.dumps(user_data, separators=(',', ':')))
        
        # Generate current timestamp
        auth_date = int(time.time())
        
        # Create the initData string components
        init_data_parts = [
            f"user={user_encoded}",
            f"chat_instance=-6598249988084805910",  # Static value from example
            f"chat_type=sender",
            f"auth_date={auth_date}"
        ]
        
        # For a real implementation, you'd need to generate proper signature and hash
        # For now, we'll use placeholder values since we need the actual bot secret
        init_data_parts.extend([
            "signature=placeholder_signature",
            "hash=placeholder_hash"
        ])
        
        return "&".join(init_data_parts)
    
    async def authenticate(self) -> bool:
        """Authenticate with stickerscan.online API"""
        try:
            # Use captured initData if available, otherwise generate it
            if TELEGRAM_INIT_DATA:
                logger.info("Using captured initData from environment")
                init_data = TELEGRAM_INIT_DATA
            else:
                # Check if we have all required telegram data for generation
                if not all([TELEGRAM_USER_ID, TELEGRAM_FIRST_NAME, TELEGRAM_USERNAME]):
                    logger.error("Missing required Telegram account data in environment variables")
                    logger.error("Either provide TELEGRAM_INIT_DATA or all manual account fields")
                    return False
                    
                logger.info("Generating initData from account data (may not work without proper signatures)")
                init_data = self._generate_init_data()
            
            payload = {
                "initData": init_data
            }
            
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            logger.info("Attempting authentication with stickerscan.online...")
            
            async with self.session.post(
                AUTH_ENDPOINT,
                json=payload,
                headers=headers
            ) as response:
                
                if response.status == 201:
                    data = await response.json()
                    self.access_token = data.get("access_token")
                    self.user_data = data.get("user")
                    
                    # Extract token expiration time (assuming JWT token)
                    if self.access_token:
                        # For JWT tokens, expiration is typically 1 hour
                        self.token_expires_at = int(time.time()) + 3600
                        
                    logger.info(f"Authentication successful. User: {self.user_data.get('firstName', 'Unknown')}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Authentication failed. Status: {response.status}, Response: {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    async def is_token_valid(self) -> bool:
        """Check if current token is still valid"""
        if not self.access_token:
            return False
            
        if self.token_expires_at and int(time.time()) >= self.token_expires_at - 300:  # 5 minutes buffer
            return False
            
        return True
    
    async def ensure_authenticated(self) -> bool:
        """Ensure we have a valid authentication token"""
        if await self.is_token_valid():
            return True
            
        return await self.authenticate()
    
    async def fetch_price_bundles(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch minimum price bundles from API"""
        try:
            if not await self.ensure_authenticated():
                logger.error("Failed to authenticate before fetching price bundles")
                return None
                
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            logger.info("Fetching price bundles...")
            
            async with self.session.get(
                PRICE_BUNDLES_ENDPOINT,
                headers=headers
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Successfully fetched {len(data)} price bundles")
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to fetch price bundles. Status: {response.status}, Response: {error_text}")
                    
                    # If unauthorized, try to re-authenticate
                    if response.status == 401:
                        logger.info("Token expired, attempting re-authentication...")
                        self.access_token = None
                        if await self.authenticate():
                            return await self.fetch_price_bundles()
                    
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching price bundles: {e}")
            return None
    
    def find_collection_by_names(self, bundles: List[Dict], collection_name: str, stickerpack_name: str) -> Optional[Dict]:
        """Find a specific collection in the price bundles"""
        for bundle in bundles:
            if (bundle.get("collectionName", "").lower() == collection_name.lower() and 
                bundle.get("characterName", "").lower() == stickerpack_name.lower()):
                return bundle
        return None
    
    def get_marketplace_prices(self, bundle: Dict) -> Dict[str, float]:
        """Extract marketplace prices from a bundle"""
        prices = {}
        marketplaces = bundle.get("marketplaces", [])
        
        for marketplace in marketplaces:
            market_name = marketplace.get("marketplace")
            if market_name == "Harbor":
                continue
            price = marketplace.get("price")
            if market_name and price is not None:
                prices[market_name] = float(price)
                
        return prices
    
    def get_lowest_price(self, bundle: Dict) -> Optional[float]:
        """Get the lowest price across all marketplaces for a bundle"""
        prices = self.get_marketplace_prices(bundle)
        if prices:
            return min(prices.values())
        return None
    
    def get_highest_price(self, bundle: Dict) -> Optional[float]:
        """Get the highest price across all marketplaces for a bundle"""
        prices = self.get_marketplace_prices(bundle)
        if prices:
            return max(prices.values())
        return None 