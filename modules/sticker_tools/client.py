import aiohttp
import logging

logger = logging.getLogger(__name__)


# TODO: Implement the approach of extracting the market data by configured collection_ids and stickerpack_ids
# TODO: Implement the analytical logic to provide short summary of volumes, count of sales and burns, and fp with mp
class StickerToolsClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        pass
