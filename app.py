import os, re, json, hashlib
from pathlib import Path
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ─── yt-dlp wrapper ──────────────────────────────────────────────────────────

def extract_info(url):
    """
    Extract media info & direct download links using yt-dlp.
    Returns list of formats with direct URLs.
    """
    import yt_dlp

    # Cookie file (for Instagram etc.) — support Vercel env var
    cookie_file = None
    insta_b64 = os.environ.get("INSTA_COOKIES_B64", "")
    if insta_b64:
        import tempfile, base64
        try:
            decoded = base64.b64decode(insta_b64).decode()
            tf = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
            tf.write(decoded)
            tf.close()
            cookie_file = tf.name
        except Exception:
            pass

    if not cookie_file:
        cookie_file = os.path.expanduser("~/.dl_bot_cookies.txt")
        if not os.path.isfile(cookie_file):
            cookie_file = None

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "no_playlist": True,
        "cookiefile": cookie_file,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        meta = ydl.extract_info(url, download=False)

    platforms = {
        "youtube": ["youtube.com", "youtu.be"],
        "tiktok": ["tiktok.com", "douyin.com"],
        "instagram": ["instagram.com", "ig.me"],
        "twitter": ["twitter.com", "x.com", "t.co"],
        "threads": ["threads.net"],
        "facebook": ["facebook.com", "fb.com", "fb.watch"],
        "soundcloud": ["soundcloud.com"],
        "spotify": ["open.spotify.com"],
        "twitch": ["twitch.tv"],
        "vimeo": ["vimeo.com"],
        "tiktok": ["tiktok.com"],
    }

    def detect_platform(u):
        ul = u.lower()
        for plat, patterns in platforms.items():
            if any(p in ul for p in patterns):
                return plat
        return "unknown"

    platform = detect_platform(url)

    # Build response
    result = {
        "title": meta.get("title", "Unknown"),
        "platform": platform,
        "thumbnail": meta.get("thumbnail", ""),
        "duration": meta.get("duration", 0),
        "webpage_url": meta.get("webpage_url", url),
        "uploader": meta.get("uploader", meta.get("channel", "")),
        "formats": [],
    }

    seen = set()
    for f in meta.get("formats", []):
        # Skip non-downloadable
        url_dl = f.get("url", "")
        if not url_dl or url_dl in seen:
            continue
        seen.add(url_dl)

        ext = f.get("ext", "unknown")
        height = f.get("height", 0) or 0
        filesize = f.get("filesize", f.get("filesize_approx", 0)) or 0
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")

        fmt = {
            "url": url_dl,
            "ext": ext,
            "height": height,
            "filesize": filesize,
            "filesize_mb": round(filesize / (1024 * 1024), 1) if filesize else 0,
            "vcodec": vcodec,
            "acodec": acodec,
            "format_note": f.get("format_note", ""),
            "format_id": f.get("format_id", ""),
            "tbr": f.get("tbr", 0),
            "fps": f.get("fps", 0) or 0,
            "resolution": f"{height}p" if height else "audio",
            "has_video": vcodec != "none",
            "has_audio": acodec != "none",
        }

        # Prioritize good quality
        result["formats"].append(fmt)

    # Sort: best video first
    result["formats"].sort(key=lambda x: (x["has_video"], x["height"], x["filesize"]), reverse=True)

    # Best single format (for quick download)
    # Pick best with both video+audio
    best = None
    for f in result["formats"]:
        if f["has_video"] and f["has_audio"]:
            best = f
            break
    if not best and result["formats"]:
        best = result["formats"][0]
    result["best"] = best

    return result


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/extract", methods=["POST"])
def api_extract():
    data = request.get_json()
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL wajib diisi"}), 400

    # Basic URL validation
    if not re.match(r"https?://[^\s]+", url):
        return jsonify({"error": "Format URL tidak valid. Gunakan link yang lengkap (https://...)"}), 400

    try:
        result = extract_info(url)
        return jsonify(result)
    except Exception as e:
        err_msg = str(e)[:300]
        return jsonify({"error": err_msg}), 422


@app.route("/api/cookies-status")
def cookies_status():
    cookie_file = os.path.expanduser("~/.dl_bot_cookies.txt")
    exists = os.path.isfile(cookie_file)
    return jsonify({
        "has_cookies": exists,
        "note": "Cookies diperlukan untuk Instagram & X/Twitter"
    })


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="donlotaja web server")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()

    print(f"🚀 donlotaja running on http://{args.host}:{args.port}")
    print(f"   📝 Paste URL → get direct download link")
    print()

    try:
        from waitress import serve
        serve(app, host=args.host, port=args.port)
    except ImportError:
        app.run(host=args.host, port=args.port, debug=args.debug)
