import aiohttp
import logging

from typing import Dict, List, Optional
from .models import CollectionStats, StickerStats, MarketTrend

logger = logging.getLogger(__name__)


class StickerToolsClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session
        self.headers = {"Accept": "*/*"}
        self.stats_base_url = "https://stickers.tools/api/stats"

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
                logger.debug(
                    f"Successfully received data of {len(response_data.get('collections', {}))} collections"
                )
                return response_data.get("collections")
            else:
                logger.error(
                    f"Unexpected error occurred. Received {response.status} HTTP code"
                )
                return None

    async def get_collection_stats(self, collection_id: str) -> Optional[CollectionStats]:
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
                collection_stats = CollectionStats.from_api(collection_id, collection_data)
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
            return f"📊 *{escape_markdown(collection.name)}* \\- No sticker data available"

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
        summary += f"💎 {total_stickers_bold} stickers \\| Avg Floor: {avg_floor_bold} TON\n"
        summary += f"📈 24h Volume: {vol_24h_bold} TON\n"
        summary += f"🔥 Active stickers: {high_volume_bold}\n\n"

        if most_active:
            most_active_name = escape_markdown(most_active.name)
            most_active_vol = f"*{escape_markdown(f'{most_active.vol_24h_ton:.1f}')}*"
            summary += f"🚀 *Most Active*: {most_active_name} \\({most_active_vol} TON\\)\n"

        if top_performer:
            change_pct = top_performer.floor_change_pct
            emoji = "📈" if change_pct > 0 else "📉"
            performer_name = escape_markdown(top_performer.name)
            change_bold = f"*{escape_markdown(f'{change_pct:+.1f}')}*%"
            summary += f"{emoji} *Top Performer*: {performer_name} \\({change_bold}\\)\n"

        if worst_performer and worst_performer != top_performer:
            change_pct = worst_performer.floor_change_pct
            emoji = "📉" if change_pct < 0 else "📈"
            performer_name = escape_markdown(worst_performer.name)
            change_bold = f"*{escape_markdown(f'{change_pct:+.1f}')}*%"
            summary += f"{emoji} *Worst Performer*: {performer_name} \\({change_bold}\\)\n"

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
            collections, 
            key=lambda c: c.total_24h_volume, 
            reverse=True
        )[:limit]

        overview = f"🌟 **Top {limit} Collections by 24h Volume**\n\n"
        
        for i, collection in enumerate(top_collections, 1):
            trend = collection.collection_trend
            volume = collection.total_24h_volume
            stickers_count = len(collection.stickers)
            overview += f"{i}. **{collection.name}** {trend.value}\n"
            overview += f"   📈 {volume:.1f} TON | 💎 {stickers_count} stickers\n\n"

        return overview
