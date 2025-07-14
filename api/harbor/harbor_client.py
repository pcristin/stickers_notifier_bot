import aiohttp
from typing import List, Dict

class HarborClient:
    def __init__(self):
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.cache_time = 60 # 1 minute

    async def __aenter__(self):
        self.session=aiohttp.ClientSession(headers=self.headers)
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.session.close()

    async def fetch_floor_price_harbor(self) -> List[Dict]:
        """
        Fetch the floor prices from the Harbor marketplace.
        Return example:
        [
            {
                "collection_name": "Azuki",
                "stickerpack_name": "Raizan",
                "wts_floor_price_ton": 28.625,
                "wtb_floor_price_ton": 21,
                "premarket_floor_price_ton": null
            },
            ...
        ]
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get("https://api.igloomarket.xyz/api/v1/stats/floor") as response:
                if response.status == 200:
                    data = await response.json()
                    return data["result"]["stickerpacks"]
                else:
                    raise Exception(f"Failed to fetch floor price: {response.status} {await response.text()}")
        return []

    async def fetch_floor_price_harbor_collection(self, collection_name: str, stickerpack_name: str) -> List[Dict]:
        """
        Fetch the floor prices from the Harbor marketplace for a specific collection.
        """
        stickerpacks = await self.fetch_floor_price_harbor()
        return [stickerpack["wts_floor_price_ton"] for stickerpack in stickerpacks if stickerpack["collection_name"] == collection_name and 
                stickerpack["stickerpack_name"] == stickerpack_name]



    