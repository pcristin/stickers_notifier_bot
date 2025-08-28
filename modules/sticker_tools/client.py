import aiohttp
import logging

from typing import Dict, List, Optional
from .models import CollectionStats, StickerStats

logger = logging.getLogger(__name__)


class StickerToolsClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session
        self.headers = {"Accept": "*/*"}
        self.stats_base_url = "https://stickers.tools/api/stats-new"

    def _normalize_sticker_payload(self, raw: dict) -> dict:
        """Normalize sticker fields from stats-new to legacy keys expected by models.

        Keeps business logic intact by mapping alternative field names
        to the existing interface used by StickerStats.from_api.
        """
        if not isinstance(raw, dict):
            return {}

        # Try multiple variants for each field to support schema changes
        def pick(keys, default=None):
            for k in keys:
                if k in raw and raw.get(k) is not None:
                    return raw.get(k)
            return default

        # Access nested structures from provided schema
        current = raw.get("current", {}) if isinstance(raw.get("current"), dict) else {}
        price_cur = current.get("price", {}) if isinstance(current.get("price"), dict) else {}
        floor_cur = price_cur.get("floor", {}) if isinstance(price_cur.get("floor"), dict) else {}
        median_cur = price_cur.get("median", {}) if isinstance(price_cur.get("median"), dict) else {}
        mcap_cur = current.get("mcap", {}) if isinstance(current.get("mcap"), dict) else {}
        mcap_cur_median = mcap_cur.get("median", {}) if isinstance(mcap_cur.get("median"), dict) else {}
        # Time windows
        d24 = raw.get("24h", {}) if isinstance(raw.get("24h"), dict) else {}
        d24_price = d24.get("price", {}) if isinstance(d24.get("price"), dict) else {}
        d24_floor = d24_price.get("floor", {}) if isinstance(d24_price.get("floor"), dict) else {}
        d24_median = d24_price.get("median", {}) if isinstance(d24_price.get("median"), dict) else {}
        d24_volume = d24.get("volume", {}) if isinstance(d24.get("volume"), dict) else {}

        d7 = raw.get("7d", {}) if isinstance(raw.get("7d"), dict) else {}
        d7_price = d7.get("price", {}) if isinstance(d7.get("price"), dict) else {}
        d7_median = d7_price.get("median", {}) if isinstance(d7_price.get("median"), dict) else {}
        d7_volume = d7.get("volume", {}) if isinstance(d7.get("volume"), dict) else {}

        # Compute derived fields
        floor_price_ton = pick(["floor_price_ton"]) or floor_cur.get("ton") or 0.0
        floor_price_24h_ton = d24_floor.get("ton") or 0.0
        floor_change_24h_ton = (floor_price_ton - floor_price_24h_ton) if (floor_price_ton is not None and floor_price_24h_ton is not None) else 0.0

        median_price_ton = pick(["median_price_ton"]) or median_cur.get("ton") or 0.0
        median_price_24h_ton = pick(["median_price_24h_ton"]) or d24_median.get("ton") or 0.0
        median_price_7d_ton = pick(["median_price_7d_ton"]) or d7_median.get("ton") or 0.0

        vol_24h_ton = pick(["24h_volume_ton", "volume_24h_ton"]) or d24_volume.get("ton") or 0.0
        vol_7d_ton = pick(["7d_volume_ton", "volume_7d_ton"]) or d7_volume.get("ton") or 0.0

        # Supply: prefer nested supply.current
        supply_block = raw.get("supply") if isinstance(raw.get("supply"), dict) else None
        supply_value = supply_block.get("current") if isinstance(supply_block, dict) else None

        # Market cap: prefer current.mcap.median.ton, fall back to alternatives
        mcap_ton = (
            pick(["mcap_ton", "market_cap_ton", "marketcap_ton"]) or mcap_cur_median.get("ton") or 0.0
        )

        return {
            "id": pick(["id", "sticker_id", "_id"], ""),
            "name": pick(["name", "title", "label"], ""),
            "supply": supply_value if supply_value is not None else pick(["supply", "circulating_supply", "total_supply"], 0),
            "floor_price_ton": floor_price_ton or 0.0,
            "floor_change_24h_ton": floor_change_24h_ton or 0.0,
            "median_price_ton": median_price_ton or 0.0,
            "median_price_24h_ton": median_price_24h_ton or 0.0,
            "median_price_7d_ton": median_price_7d_ton or 0.0,
            "24h_volume_ton": vol_24h_ton or 0.0,
            "7d_volume_ton": vol_7d_ton or 0.0,
            "total_sales": pick(["total_sales", "sales_total", "sales", "trades"], 0) or 0,
            "mcap_ton": mcap_ton or 0.0,
        }

    def _normalize_collections_payload(self, response_data: dict) -> Optional[Dict]:
        """Normalize /api/stats-new response into {collection_id: {...}} shape.

        Accepts various plausible shapes (dict with collections, list of collections,
        or nested under a data key) and returns a dict keyed by collection id with
        legacy-compatible fields for downstream parsing.
        """
        if not isinstance(response_data, dict):
            return None

        collections = None

        # Common top-level locations
        if isinstance(response_data.get("collections"), (dict, list)):
            collections = response_data.get("collections")
        elif isinstance(response_data.get("data"), dict) and isinstance(
            response_data["data"].get("collections"), (dict, list)
        ):
            collections = response_data["data"].get("collections")
        elif isinstance(response_data.get("data"), list):
            collections = response_data.get("data")
        elif isinstance(response_data.get("result"), dict) and isinstance(
            response_data["result"].get("collections"), (dict, list)
        ):
            collections = response_data["result"].get("collections")
        else:
            # If response itself looks like a collections dict
            if all(isinstance(v, dict) for v in response_data.values()):
                collections = response_data

        if collections is None:
            return None

        # If already a dict keyed by id, still normalize stickers
        if isinstance(collections, dict):
            normalized = {}
            for cid, cval in collections.items():
                if not isinstance(cval, dict):
                    continue
                # Normalize stickers field: can be dict keyed by id or a list
                stickers = cval.get("stickers")
                if stickers is None:
                    stickers = cval.get("items") or cval.get("characters") or []
                # Convert dict of stickers to list of values
                if isinstance(stickers, dict):
                    stickers_iter = stickers.values()
                elif isinstance(stickers, list):
                    stickers_iter = stickers
                else:
                    stickers_iter = []
                stickers = [self._normalize_sticker_payload(s) for s in stickers_iter]

                normalized[cid] = {
                    "name": cval.get("name") or cval.get("title") or cval.get("collection_name") or "",
                    # Collection-level totals from nested structures
                    "total_mcap_ton": (
                        (cval.get("mcap") or {}).get("median", {}).get("ton")
                        if isinstance(cval.get("mcap"), dict)
                        else None
                    ) or cval.get("total_mcap_ton") or cval.get("mcap_ton") or cval.get("market_cap_ton") or 0.0,
                    "total_volume_ton": (
                        (cval.get("total_volume") or {}).get("ton")
                        if isinstance(cval.get("total_volume"), dict)
                        else None
                    ) or cval.get("total_volume_ton") or cval.get("volume_ton") or cval.get("total_vol_ton") or 0.0,
                    "stickers": stickers or [],
                }
            return normalized

        # If list of collection objects, convert to dict keyed by id
        if isinstance(collections, list):
            normalized = {}
            for c in collections:
                if not isinstance(c, dict):
                    continue
                cid = (
                    str(c.get("id")
                        or c.get("collection_id")
                        or c.get("_id")
                        or "")
                )
                if not cid:
                    # Fallback: try name as id (last resort)
                    cid = str(c.get("name") or c.get("title") or c.get("collection_name") or "")

                stickers = c.get("stickers") or c.get("items") or c.get("characters") or []
                if isinstance(stickers, dict):
                    stickers_iter = stickers.values()
                elif isinstance(stickers, list):
                    stickers_iter = stickers
                else:
                    stickers_iter = []
                stickers = [self._normalize_sticker_payload(s) for s in stickers_iter]

                normalized[cid] = {
                    "name": c.get("name") or c.get("title") or c.get("collection_name") or "",
                    "total_mcap_ton": (
                        (c.get("mcap") or {}).get("median", {}).get("ton")
                        if isinstance(c.get("mcap"), dict)
                        else None
                    ) or c.get("total_mcap_ton") or c.get("mcap_ton") or c.get("market_cap_ton") or 0.0,
                    "total_volume_ton": (
                        (c.get("total_volume") or {}).get("ton")
                        if isinstance(c.get("total_volume"), dict)
                        else None
                    ) or c.get("total_volume_ton") or c.get("volume_ton") or c.get("total_vol_ton") or 0.0,
                    "stickers": stickers or [],
                }
            return normalized

        return None

    async def get_all_stats(self) -> Optional[Dict]:
        """Get all general historical data about all current stickerpacks

        Returns:
            None or collections dict where each key corresponds to collection id and contain stickerpacks info
        """
        async with self.session.get(
            url=self.stats_base_url,
            headers=self.headers,
        ) as response:
            if response.status == 200:
                response_data = await response.json()
                normalized = self._normalize_collections_payload(response_data)
                count = len(normalized or {})
                if normalized is None:
                    logger.error("stats-new: Unable to find collections in response payload")
                    return None
                logger.debug(f"Successfully received data of {count} collections")
                return normalized
            else:
                logger.error(
                    f"Unexpected error occurred. Received {response.status} HTTP code"
                )
                return None

    async def get_collection_stats(
        self, collection_id: str
    ) -> Optional[CollectionStats]:
        """Get parsed statistics for a specific collection

        Args:
            collection_id: ID of the collection to analyze

        Returns:
            CollectionStats object or None if not found
        """
        all_stats = await self.get_all_stats()
        if not all_stats or collection_id not in all_stats:
            logger.warning(f"Collection {collection_id} not found")
            return None

        try:
            return CollectionStats.from_api(collection_id, all_stats[collection_id])
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing collection {collection_id}: {e}")
            return None

    async def get_all_collections(self) -> List[CollectionStats]:
        """Get all collections as parsed CollectionStats objects

        Returns:
            List of CollectionStats objects
        """
        all_stats = await self.get_all_stats()
        if not all_stats:
            return []

        collections = []
        for collection_id, collection_data in all_stats.items():
            try:
                collection_stats = CollectionStats.from_api(
                    collection_id, collection_data
                )
                collections.append(collection_stats)
            except (KeyError, ValueError) as e:
                logger.error(f"Error parsing collection {collection_id}: {e}")
                continue

        return collections

    async def find_collection_by_name(self, name: str) -> Optional[CollectionStats]:
        """Find collection by name (case-insensitive)

        Args:
            name: Collection name to search for

        Returns:
            CollectionStats object or None if not found
        """
        collections = await self.get_all_collections()
        name_lower = name.lower()

        for collection in collections:
            if collection.name.lower() == name_lower:
                return collection

        # Try partial match
        for collection in collections:
            if name_lower in collection.name.lower():
                return collection

        return None

    def generate_collection_summary(self, collection: CollectionStats) -> str:
        """Generate a concise summary of collection performance

        Args:
            collection: CollectionStats object to summarize

        Returns:
            Formatted string with key insights (MarkdownV2 format)
        """
        from utils import escape_markdown

        if not collection.stickers:
            return (
                f"📊 *{escape_markdown(collection.name)}* \\- No sticker data available"
            )

        # Basic stats
        total_stickers = len(collection.stickers)
        avg_floor = collection.avg_floor_price
        total_24h_vol = collection.total_24h_volume
        trend = collection.collection_trend

        # Key insights
        most_active = collection.most_active_sticker
        top_performer = collection.top_performer
        worst_performer = collection.worst_performer
        high_volume_count = len(collection.high_volume_stickers)

        # Escape and format with bold numbers
        collection_name = escape_markdown(collection.name)
        total_stickers_bold = f"*{escape_markdown(str(total_stickers))}*"
        avg_floor_bold = f"*{escape_markdown(f'{avg_floor:.1f}')}*"
        vol_24h_bold = f"*{escape_markdown(f'{total_24h_vol:.1f}')}*"
        high_volume_bold = f"*{escape_markdown(str(high_volume_count))}*"

        summary = f"📊 *{collection_name}* {trend.value}\n\n"
        summary += (
            f"💎 {total_stickers_bold} stickers \\| Avg Floor: {avg_floor_bold} TON\n"
        )
        summary += f"📈 24h Volume: {vol_24h_bold} TON\n"
        summary += f"🔥 Active stickers: {high_volume_bold}\n\n"

        if most_active:
            most_active_name = escape_markdown(most_active.name)
            most_active_vol = f"*{escape_markdown(f'{most_active.vol_24h_ton:.1f}')}*"
            summary += (
                f"🚀 *Most Active*: {most_active_name} \\({most_active_vol} TON\\)\n"
            )

        if top_performer:
            change_pct = top_performer.floor_change_pct
            emoji = "📈" if change_pct > 0 else "📉"
            performer_name = escape_markdown(top_performer.name)
            change_bold = f"*{escape_markdown(f'{change_pct:+.1f}')}*%"
            summary += (
                f"{emoji} *Top Performer*: {performer_name} \\({change_bold}\\)\n"
            )

        if worst_performer and worst_performer != top_performer:
            change_pct = worst_performer.floor_change_pct
            emoji = "📉" if change_pct < 0 else "📈"
            performer_name = escape_markdown(worst_performer.name)
            change_bold = f"*{escape_markdown(f'{change_pct:+.1f}')}*%"
            summary += (
                f"{emoji} *Worst Performer*: {performer_name} \\({change_bold}\\)\n"
            )

        return summary

    def generate_sticker_details(self, sticker: StickerStats) -> str:
        """Generate detailed analysis for a specific sticker

        Args:
            sticker: StickerStats object to analyze

        Returns:
            Formatted string with detailed metrics (MarkdownV2 format)
        """
        from utils import escape_markdown

        trend = sticker.price_trend
        vol_change = sticker.vol_change_pct
        floor_change = sticker.floor_change_pct
        median_change = sticker.median_change_pct

        # Escape and format with bold numbers
        sticker_name = escape_markdown(sticker.name)
        floor_price_bold = f"*{escape_markdown(f'{sticker.floor_price_ton:.1f}')}*"
        floor_change_bold = f"*{escape_markdown(f'{floor_change:+.1f}')}*%"
        median_price_bold = f"*{escape_markdown(f'{sticker.median_price_ton:.1f}')}*"
        vol_24h_bold = f"*{escape_markdown(f'{sticker.vol_24h_ton:.1f}')}*"
        supply_bold = f"*{escape_markdown(f'{sticker.supply:,}')}*"
        sales_bold = f"*{escape_markdown(f'{sticker.total_sales:,}')}*"
        mcap_bold = f"*{escape_markdown(f'{sticker.mcap_ton:.0f}')}*"

        details = f"🎯 *{sticker_name}* {trend.value}\n\n"
        details += f"💰 *Floor*: {floor_price_bold} TON \\({floor_change_bold}\\)\n"

        # Median price with change
        if median_change is not None:
            median_change_bold = f"*{escape_markdown(f'{median_change:+.1f}')}*%"
            details += f"📊 *Median*: {median_price_bold} TON \\({median_change_bold} vs 7d\\)\n"
        else:
            details += f"📊 *Median*: {median_price_bold} TON\n"

        # Volume with change analysis
        if vol_change is not None:
            vol_emoji = "🚀" if vol_change > 50 else "📈" if vol_change > 0 else "📉"
            vol_change_bold = f"*{escape_markdown(f'{vol_change:+.1f}')}*%"
            details += f"{vol_emoji} *24h Volume*: {vol_24h_bold} TON \\({vol_change_bold} vs avg\\)\n"
        else:
            details += f"📈 *24h Volume*: {vol_24h_bold} TON\n"

        details += f"🏭 *Supply*: {supply_bold} \\| *Sales*: {sales_bold}\n"
        details += f"💎 *Market Cap*: {mcap_bold} TON\n"

        # Activity level
        if sticker.is_high_volume:
            details += "\n🔥 *High trading activity*"
        else:
            details += "\n😴 *Low trading activity*"

        return details

    async def get_market_overview(self, limit: int = 10) -> str:
        """Generate overview of top collections by volume

        Args:
            limit: Number of top collections to include

        Returns:
            Formatted market overview string
        """
        collections = await self.get_all_collections()
        if not collections:
            return "❌ No market data available"

        # Sort by 24h volume
        top_collections = sorted(
            collections, key=lambda c: c.total_24h_volume, reverse=True
        )[:limit]

        overview = f"🌟 **Top {limit} Collections by 24h Volume**\n\n"

        for i, collection in enumerate(top_collections, 1):
            trend = collection.collection_trend
            volume = collection.total_24h_volume
            stickers_count = len(collection.stickers)
            overview += f"{i}. **{collection.name}** {trend.value}\n"
            overview += f"   📈 {volume:.1f} TON | 💎 {stickers_count} stickers\n\n"

        return overview
