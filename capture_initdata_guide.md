# How to Capture initData from Browser

## Step-by-Step Guide

### 1. Open stickerscan.online
- Go to [https://stickerscan.online](https://stickerscan.online) in your browser
- Make sure you're logged out first (if previously logged in)

### 2. Open Developer Tools
- Press `F12` (or `Ctrl+Shift+I` on Windows/Linux, `Cmd+Option+I` on Mac)
- Click on the **Network** tab
- Check "Preserve log" option to keep requests during navigation

### 3. Start Login Process
- Click on the login/connect button on stickerscan.online
- This will open a Telegram WebApp authentication popup

### 4. Complete Telegram Authentication
- Authorize the webapp in Telegram
- This will redirect you back to stickerscan.online

### 5. Find the Authentication Request
- In the Network tab, look for a POST request to `/auth/telegram`
- The URL should be: `https://stickerscan.online/api/auth/telegram`
- Click on this request

### 6. Extract initData
- In the request details, look for the **Request Payload** section
- You'll see something like:
  ```json
  {
    "initData": "user=%7B%22id%22%3A27826076%2C%22first_name%22%3A%22Oleg%22..."
  }
  ```

### 7. Copy the initData Value
- Copy the entire string after `"initData": "` (without the surrounding quotes)
- This is a long URL-encoded string that contains your Telegram account data and authentication signatures

### 8. Add to .env File
- Open your `.env` file
- Add the line:
  ```
  TELEGRAM_INIT_DATA=your_copied_initdata_string_here
  ```

## Example initData Format

The initData should look something like this (this is just an example):
```
user=%7B%22id%22%3A27826076%2C%22first_name%22%3A%22Oleg%22%2C%22last_name%22%3A%22%22%2C%22username%22%3A%22okz_09%22%2C%22language_code%22%3A%22en%22%2C%22is_premium%22%3Atrue%2C%22allows_write_to_pm%22%3Atrue%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2Fe_Fi26otzpLa855UJWA8L5agxLkcTWtcAm3TQm3TDB8.svg%22%7D&chat_instance=-6598249988084805910&chat_type=sender&auth_date=1752218284&signature=qy86qwaBzZx7-Zvtl4Gzj1B-rARgG3Fd4vQgA-8W7dH3Qy33OivMUB0j5pWtPDi5kDREx9URUS6CQuW9qpRXDg&hash=0dc7deb17e8a7100a834c4d95acd5f9aa7d13f619b91718ceed846e48c20ac86
```

## Important Notes

- **Security**: The initData contains authentication signatures that expire. You may need to recapture it periodically.
- **Privacy**: This data contains your Telegram account information. Keep your `.env` file secure.
- **Expiration**: initData typically expires after some time (usually hours or days). If you start getting 401 errors again, recapture it.

## Testing Your Captured Data

After adding the initData to your `.env` file, test it:

```bash
python test_auth.py
```

If successful, you should see:
```
✅ Authentication successful!
👤 User: YourName
🔑 Token received: XXX characters
```

## Troubleshooting

**Problem**: Can't find `/auth/telegram` request
- **Solution**: Make sure you clear the network log and try the login process again

**Problem**: initData shows as "Invalid initData"
- **Solution**: Make sure you copied the entire string correctly, including all URL encoding

**Problem**: 401 Unauthorized error
- **Solution**: The initData may have expired. Recapture it from a fresh browser session 