import json
import hashlib
import hmac
import time
import urllib.parse
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, parse_qsl, unquote_plus
import aiohttp
import logging
from telethon import TelegramClient, functions, types

from config import (
    AUTH_ENDPOINT, PRICE_BUNDLES_ENDPOINT,
        TELEGRAM_INIT_DATA, TELEGRAM_API_ID, TELEGRAM_API_HASH
)

logger = logging.getLogger(__name__)

class Scanner:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.access_token: Optional[str] = None
        self.user_data: Optional[Dict] = None
        self.token_expires_at: Optional[int] = None
        
        # Telethon config
        self.api_id = TELEGRAM_API_ID
        self.api_hash = TELEGRAM_API_HASH
        self.bot_username = '@sticker_scan_bot'
        self.peer = '@sticker_scan_bot'
        self.base_webapp = 'https://stickerscan.online/api/auth/telegram'
        
    async def _get_webapp_url(self) -> str:
        """Get webapp URL using Telethon"""
        client = TelegramClient('session', self.api_id, self.api_hash)
        await client.start()
        
        try:
            res = await client(functions.messages.RequestWebViewRequest(
                peer=self.peer,
                bot=self.bot_username,
                platform='web',
                from_bot_menu=True,
                url=self.base_webapp,
                theme_params=types.DataJSON(data='{}'),
            ))
            return res.url
        finally:
            await client.disconnect()
    
    def _fragment_to_initdata(self, frag: str) -> str:
        """
        Extract initData from URL fragment.
        Given the URL-fragment after the '#', extract exactly
        the 'tgWebAppData=...' payload and turn it into the
        string the WebApp POST uses.
        """
        pairs = dict(parse_qsl(frag, keep_blank_values=True))
        raw = pairs.get('tgWebAppData')
        if not raw:
            raise ValueError("No tgWebAppData in fragment")
        # raw is URL-encoded again, so decode it once
        return unquote_plus(raw)
    
    async def _get_telethon_initdata(self) -> str:
        """Get initData using Telethon authentication"""
        # 1) get the MTProto‑generated WebView URL
        webview_url = await self._get_webapp_url()
        logger.info(f"WebView URL obtained: {webview_url}")
        
        # 2) pull off the "#..." fragment
        frag = urlparse(webview_url).fragment
        init_data = self._fragment_to_initdata(frag)
        logger.info("initData extracted from WebView URL")
        
        return init_data
        
    async def authenticate(self) -> bool:
        """Authenticate with stickerscan.online API using Telethon"""
        try:
            # Use captured initData if available, otherwise get it via Telethon
            if TELEGRAM_INIT_DATA:
                logger.info("Using captured initData from environment")
                init_data = TELEGRAM_INIT_DATA
            else:
                logger.info("Getting initData via Telethon...")
                init_data = await self._get_telethon_initdata()
            
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
            price = marketplace.get("price")
            if market_name and price is not None:
                prices[market_name] = float(price)
                
        return prices
    
    def get_marketplace_data(self, bundle: Dict) -> Dict[str, Dict[str, any]]:
        """Extract marketplace data including prices and URLs from a bundle"""
        marketplace_data = {}
        marketplaces = bundle.get("marketplaces", [])
        
        for marketplace in marketplaces:
            market_name = marketplace.get("marketplace")
            price = marketplace.get("price")
            url = marketplace.get("url")
            
            if market_name and price is not None:
                marketplace_data[market_name] = {
                    "price": float(price),
                    "url": url
                }
                
        return marketplace_data
    
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