from typing import TypedDict, Union


# Stats_7D is abstract structure for better annotations
# the whole data is defined inside data as list of dicts
class Stats_7D(TypedDict):
    date: str
    sales_count: int
    volume_ton: float
    volume_usd: float
    median_price_ton: float
    mdeian_price_usd: float
    floor_price_ton: float
    floor_price_usd: float
    burn_count: Union[None, int]
