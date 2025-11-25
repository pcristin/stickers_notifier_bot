from typing import Dict, List, Optional, Any, TypedDict
import aiohttp
import logging

from config import STICKER_STATS_ENDPOINT

logger = logging.getLogger(__name__)


# MarketEntry is TypedDict class for annotation clarity
class MarketEntry(TypedDict):
    price: float
    url: Optional[str]


class Scanner:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.stats_endpoint = STICKER_STATS_ENDPOINT

    async def fetch_price_bundles(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch sticker statistics from stickers.tools and normalize output."""
        try:
            logger.info("Fetching sticker statistics from stickers.tools...")
            async with self.session.get(
                self.stats_endpoint,
                headers={"Accept": "application/json"},
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        "Failed to fetch sticker statistics. Status: %s, Response: %s",
                        response.status,
                        error_text,
                    )
                    return None

                payload = await response.json()
                bundles = self._transform_stats_payload(payload)
                logger.info("Successfully fetched %s sticker entries", len(bundles))
                return bundles
        except Exception as e:
            logger.error(f"Error fetching sticker statistics: {e}")
            return None

    def _transform_stats_payload(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert stickers.tools stats payload into legacy bundle structure."""
        collections = data.get("collections")
        if not isinstance(collections, dict):
            logger.error("stats-new payload missing collections dictionary")
            return []

        bundles: List[Dict[str, Any]] = []
        for collection_id, collection_data in collections.items():
            if not isinstance(collection_data, dict):
                continue

            collection_name = collection_data.get("name", "")
            stickers = collection_data.get("stickers")
            if isinstance(stickers, dict):
                sticker_iterable = stickers.values()
            elif isinstance(stickers, list):
                sticker_iterable = stickers
            else:
                sticker_iterable = []

            for sticker_data in sticker_iterable:
                if not isinstance(sticker_data, dict):
                    continue

                bundle = self._build_bundle(collection_id, collection_name, sticker_data)
                if bundle:
                    bundles.append(bundle)

        return bundles

    def _build_bundle(
        self, collection_id: Any, collection_name: str, sticker_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        sticker_name = sticker_data.get("name")
        if not sticker_name:
            return None

        floor_price = self._extract_nested_float(
            sticker_data, ["current", "price", "floor", "ton"]
        )
        image_url = sticker_data.get("preview_url")
        sticker_id = sticker_data.get("id")

        market_entry: List[Dict[str, Any]] = []
        if floor_price is not None:
            market_info = {
                "marketplace": "STICKERS_TOOLS",
                "price": floor_price,
                "currency": "TON",
                "prices": [],
                "url": self._build_sticker_url(collection_id, sticker_id),
            }
            market_entry.append(market_info)

        bundle = {
            "collectionId": str(collection_id),
            "collectionName": collection_name,
            "characterId": str(sticker_id),
            "characterName": sticker_name,
            "imageUrl": image_url,
            "marketplaces": market_entry,
            "stats": self._extract_stats_snapshot(sticker_data),
        }

        return bundle

    def _extract_stats_snapshot(self, sticker_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract a compact stats snapshot for downstream features."""
        current = sticker_data.get("current") if isinstance(sticker_data.get("current"), dict) else {}
        price_block = current.get("price") if isinstance(current.get("price"), dict) else {}
        volume_block = current.get("volume") if isinstance(current.get("volume"), dict) else {}

        return {
            "floor_price_ton": self._extract_nested_float(price_block, ["floor", "ton"]),
            "median_price_ton": self._extract_nested_float(price_block, ["median", "ton"]),
            "24h_volume_ton": self._extract_nested_float(sticker_data, ["24h", "volume", "ton"]),
            "7d_volume_ton": self._extract_nested_float(sticker_data, ["7d", "volume", "ton"]),
            "current_volume_ton": self._extract_nested_float(volume_block, ["ton"]),
        }

    def _extract_nested_float(self, data: Dict[str, Any], path: List[str]) -> Optional[float]:
        node: Any = data
        for key in path:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        try:
            if node is None:
                return None
            return float(node)
        except (TypeError, ValueError):
            return None

    def _build_sticker_url(self, collection_id: Any, sticker_id: Any) -> Optional[str]:
        if collection_id is None or sticker_id is None:
            return None
        return f"https://assets.tools/collection/{collection_id}?sticker={sticker_id}"

    def find_collection_by_names(
        self, bundles: List[Dict], collection_name: str, stickerpack_name: str
    ) -> Optional[Dict]:
        """Find a specific collection in the price bundles"""
        for bundle in bundles:
            if (
                bundle.get("collectionName", "").lower() == collection_name.lower()
                and bundle.get("characterName", "").lower() == stickerpack_name.lower()
            ):
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

    def get_marketplace_data(self, bundle: Dict) -> Dict[str, MarketEntry]:
        """Extract marketplace data including prices and URLs from a bundle"""
        marketplace_data = {}
        marketplaces = bundle.get("marketplaces", [])

        for marketplace in marketplaces:
            market_name = marketplace.get("marketplace")
            price = marketplace.get("price")
            url = marketplace.get("url")

            if market_name and price is not None:
                marketplace_data[market_name] = {"price": float(price), "url": url}

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
