from dataclasses import dataclass
from typing import List, Optional, Self
from enum import Enum


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert value to float, returning default if None or invalid"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default: int = 0) -> int:
    """Safely convert value to int, returning default if None or invalid"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


class MarketTrend(Enum):
    BULLISH = "📈"
    BEARISH = "📉"
    NEUTRAL = "➡️"


@dataclass(slots=True)
class StickerStats:
    """Individual sticker statistics and metrics"""
    id: str
    name: str
    supply: int
    floor_price_ton: float
    floor_change_24h_ton: float
    median_price_ton: float
    median_price_24h_ton: float
    median_price_7d_ton: float
    vol_24h_ton: float
    vol_7d_ton: float
    total_sales: int
    mcap_ton: float

    @classmethod
    def from_api(cls, raw: dict) -> Self:
        """Extract sticker data from API response"""
        return cls(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            supply=safe_int(raw.get("supply")),
            floor_price_ton=safe_float(raw.get("floor_price_ton")),
            floor_change_24h_ton=safe_float(raw.get("floor_change_24h_ton")),
            median_price_ton=safe_float(raw.get("median_price_ton")),
            median_price_24h_ton=safe_float(raw.get("median_price_24h_ton")),
            median_price_7d_ton=safe_float(raw.get("median_price_7d_ton")),
            vol_24h_ton=safe_float(raw.get("24h_volume_ton")),
            vol_7d_ton=safe_float(raw.get("7d_volume_ton")),
            total_sales=safe_int(raw.get("total_sales")),
            mcap_ton=safe_float(raw.get("mcap_ton")),
        )

    @property
    def vol_change_pct(self) -> Optional[float]:
        """24h vs 7d volume change percentage"""
        if self.vol_7d_ton == 0:
            return None
        daily_avg_7d = self.vol_7d_ton / 7
        return (self.vol_24h_ton / daily_avg_7d - 1) * 100 if daily_avg_7d > 0 else None

    @property
    def floor_change_pct(self) -> float:
        """Floor price change percentage"""
        if self.floor_price_ton == 0:
            return 0.0
        return (self.floor_change_24h_ton / self.floor_price_ton) * 100

    @property
    def median_change_pct(self) -> Optional[float]:
        """Median price change percentage (24h vs 7d)"""
        if self.median_price_7d_ton == 0:
            return None
        return ((self.median_price_24h_ton / self.median_price_7d_ton) - 1) * 100

    @property
    def price_trend(self) -> MarketTrend:
        """Determine overall price trend"""
        floor_trend = self.floor_change_pct
        median_trend = self.median_change_pct or 0
        
        avg_trend = (floor_trend + median_trend) / 2
        
        if avg_trend > 5:
            return MarketTrend.BULLISH
        elif avg_trend < -5:
            return MarketTrend.BEARISH
        else:
            return MarketTrend.NEUTRAL

    @property
    def is_high_volume(self) -> bool:
        """Check if sticker has significant trading volume"""
        # Avoid division by zero if floor price is 0
        if self.floor_price_ton == 0:
            return self.vol_24h_ton > 10  # Fallback to 10 TON threshold
        return self.vol_24h_ton > 10 * self.floor_price_ton


@dataclass(slots=True)
class CollectionStats:
    """Collection-level statistics and insights"""
    id: str
    name: str
    total_mcap_ton: float
    total_volume_ton: float
    stickers: List[StickerStats]

    @classmethod
    def from_api(cls, collection_id: str, raw: dict) -> Self:
        """Extract collection data from API response"""
        stickers = [StickerStats.from_api(sticker_data) for sticker_data in raw.get("stickers", [])]
        
        return cls(
            id=str(collection_id),
            name=str(raw.get("name", "")),
            total_mcap_ton=safe_float(raw.get("total_mcap_ton")),
            total_volume_ton=safe_float(raw.get("total_volume_ton")),
            stickers=stickers,
        )

    @property
    def total_24h_volume(self) -> float:
        """Sum of all stickers 24h volume"""
        return sum(sticker.vol_24h_ton for sticker in self.stickers)

    @property
    def avg_floor_price(self) -> float:
        """Average floor price across all stickers"""
        if not self.stickers:
            return 0
        return sum(sticker.floor_price_ton for sticker in self.stickers) / len(self.stickers)

    @property
    def most_active_sticker(self) -> Optional[StickerStats]:
        """Sticker with highest 24h volume"""
        if not self.stickers:
            return None
        return max(self.stickers, key=lambda s: s.vol_24h_ton)

    @property
    def top_performer(self) -> Optional[StickerStats]:
        """Sticker with highest floor price change"""
        if not self.stickers:
            return None
        return max(self.stickers, key=lambda s: s.floor_change_pct)

    @property
    def worst_performer(self) -> Optional[StickerStats]:
        """Sticker with lowest floor price change"""
        if not self.stickers:
            return None
        return min(self.stickers, key=lambda s: s.floor_change_pct)

    @property
    def high_volume_stickers(self) -> List[StickerStats]:
        """Stickers with significant trading activity"""
        return [sticker for sticker in self.stickers if sticker.is_high_volume]

    @property
    def collection_trend(self) -> MarketTrend:
        """Overall collection trend based on average performance"""
        if not self.stickers:
            return MarketTrend.NEUTRAL
            
        avg_floor_change = sum(s.floor_change_pct for s in self.stickers) / len(self.stickers)
        
        if avg_floor_change > 5:
            return MarketTrend.BULLISH
        elif avg_floor_change < -5:
            return MarketTrend.BEARISH
        else:
            return MarketTrend.NEUTRAL
