# donlotaja

Multi-platform downloader web app. Paste link YouTube, TikTok, Instagram, X/Twitter, Threads, Facebook, SoundCloud — dapatkan tautan download langsung.

## Fitur

- ✅ YouTube (hingga 4K)
- ✅ TikTok (video tanpa watermark)
- ✅ Instagram (reels, posts — butuh cookies)
- ✅ X/Twitter (video, GIF)
- ✅ Threads, Facebook, SoundCloud, Spotify, dan 1000+ platform lainnya via yt-dlp
- ✅ Tautan download langsung — nggak perlu download ulang ke server
- ✅ Mobile-first, dark mode
- ✅ Copy link atau download langsung

## Cara Jalankan

```bash
# Install dependencies
pip install -r requirements.txt

# Jalankan
python app.py

# Atau dengan port kustom
python app.py --port 8080

# Atau dengan waitress (production)
python app.py
```

Buka `http://localhost:5000` di browser.

## Cookies (Instagram & X/Twitter)

Untuk Instagram dan X/Twitter, export cookies dari browser:

1. Login ke Instagram/X di browser
2. Export cookies (Netscape format) ke `~/.dl_bot_cookies.txt`
3. Restart web app

## Deploy

Bisa dijalankan di:
- **Termux/Android** — langsung `python app.py`
- **VPS/Raspberry Pi** — pakai systemd + reverse proxy
- **Railway/Render/Heroku** — ubah port ke `$PORT`

## Lisensi

MIT
