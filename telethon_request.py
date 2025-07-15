import asyncio
import re
from urllib.parse import urlparse, parse_qsl, unquote_plus

import requests
from telethon import TelegramClient, functions, types
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH

# ── CONFIG ────────────────────────────────────────────────────────────────
# 1) Your user API credentials from https://my.telegram.org
api_id   = TELEGRAM_API_ID
api_hash = TELEGRAM_API_HASH

# 2) The bot that hosts the WebApp, and the chat/user where you opened it
bot_username = '@sticker_scan_bot'
peer         = '@sticker_scan_bot'

# 3) The *original* WebApp URL that the bot registered
#    (you don't need tgWebAppInitData here — Telethon will get it for you)
base_webapp = 'https://stickerscan.online/api/auth/telegram'
# ── END CONFIG ────────────────────────────────────────────────────────────


async def get_webapp_url():
    client = TelegramClient('session', api_id, api_hash)
    await client.start()  # phone+code on first run

    res = await client(functions.messages.RequestWebViewRequest(
        peer         = peer,
        bot          = bot_username,
        platform     = 'web',
        from_bot_menu= True,
        compact      = True,
        fullscreen   = False,
        url          = base_webapp,
        start_param  = None,
        theme_params = types.DataJSON(data='{}'),
    ))
    await client.disconnect()
    return res.url

def fragment_to_initdata(frag: str) -> str:
    """
    Given the URL-fragment after the '#', extract exactly
    the 'tgWebAppData=...' payload and turn it into the
    string the WebApp POST uses (i.e. the right-hand side
    of that =, URL-decoded).
    """
    # frag looks like: "tgWebAppData=query_id%3D…%26user%3D…%26…&tgWebAppVersion=…&tgWebAppPlatform=…"
    # we only care about the value of tgWebAppData
    pairs = dict(parse_qsl(frag, keep_blank_values=True))
    raw = pairs.get('tgWebAppData')
    if not raw:
        raise ValueError("No tgWebAppData in fragment")
    # raw is URL-encoded again, so decode it once
    return unquote_plus(raw)

def call_sticker_scan(init_data: str):
    """
    POST to the sticker_scan bot backend exactly as the web-app does.
    """
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (TelegramBot WebApp)'
    }
    payload = {
        'initData': init_data
    }
    r = requests.post(base_webapp, json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

async def main():
    # 1) get the MTProto‑generated WebView URL
    webview_url = await get_webapp_url()
    print('→ WebView URL:', webview_url)

    # 2) pull off the "#..." fragment
    frag = urlparse(webview_url).fragment
    init_data = fragment_to_initdata(frag)
    print('\n→ initData string:')
    print(init_data)

    # 3) do the POST just like the real WebApp
    resp = call_sticker_scan(init_data)
    print('\n✅ sticker_scan response:')
    print(resp)

if __name__ == '__main__':
    asyncio.run(main())