import os, re, json, hashlib, urllib.request, tempfile, base64
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, redirect

app = Flask(__name__)

# ─── Helpers ───────────────────────────────────────────────────────────────────

def get_cookie_file():
    """Get yt-dlp compatible cookie file from env or local path."""
    cookie_file = None
    insta_b64 = os.environ.get("INSTA_COOKIES_B64", "")
    if insta_b64:
        try:
            raw = base64.b64decode(insta_b64).decode()
            tab_lines = ["# Netscape HTTP Cookie File", "# Auto-converted", ""]
            for line in raw.strip().split("\n"):
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 7:
                    tab_line = "\t".join([parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], " ".join(parts[6:])])
                    tab_lines.append(tab_line)
            tf = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
            tf.write("\n".join(tab_lines) + "\n")
            tf.close()
            cookie_file = tf.name
        except Exception:
            pass

    if not cookie_file:
        cookie_file = os.path.expanduser("~/.dl_bot_cookies.txt")
        if not os.path.isfile(cookie_file):
            cookie_file = None
    return cookie_file


def get_filesize_mb(direct_url):
    """Try to get file size from a direct URL via HEAD request."""
    if not direct_url:
        return 0
    try:
        req = urllib.request.Request(direct_url, method="HEAD")
        # Some CDNs need user-agent
        req.add_header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")
        with urllib.request.urlopen(req, timeout=8) as resp:
            length = resp.headers.get("Content-Length")
            if length:
                return round(int(length) / (1024 * 1024), 1)
    except Exception:
        pass
    return 0


def extract_info(url):
    """Extract media info & direct download links using yt-dlp."""
    import yt_dlp

    cookie_file = get_cookie_file()

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
    }

    def detect_platform(u):
        ul = u.lower()
        for plat, patterns in platforms.items():
            if any(p in ul for p in patterns):
                return plat
        return "unknown"

    platform = detect_platform(url)

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
        url_dl = f.get("url", "")
        if not url_dl or url_dl in seen:
            continue
        seen.add(url_dl)

        ext = f.get("ext", "unknown")
        height = f.get("height", 0) or 0
        filesize = f.get("filesize", f.get("filesize_approx", 0)) or 0
        raw_vcodec = f.get("vcodec")
        raw_acodec = f.get("acodec")

        # Determine has_video / has_audio:
        # DASH formats: vcodec="none"/acodec="none" => video-only/audio-only
        # Progressive formats (e.g. IG): vcodec=None, acodec=None/missing => has both
        # Regular formats: explicit vcodec/acodec strings
        has_video = raw_vcodec is not None and raw_vcodec != "none"
        has_audio = raw_acodec is not None and raw_acodec != "none"

        # Progressive/raw format: both codecs unset but format has both tracks
        if raw_vcodec is None and raw_acodec is None:
            has_video = True
            has_audio = True
        # Shouldn't happen, but handle edge cases
        elif raw_vcodec is not None and raw_vcodec != "none" and raw_acodec is None:
            has_video = True
            has_audio = False
        elif raw_acodec is not None and raw_acodec != "none" and raw_vcodec is None:
            has_video = False
            has_audio = True

        filesize_mb = round(filesize / (1024 * 1024), 1) if filesize else 0

        fmt = {
            "url": url_dl,
            "ext": ext,
            "height": height,
            "filesize": filesize,
            "filesize_mb": filesize_mb,
            "format_note": f.get("format_note", ""),
            "format_id": f.get("format_id", ""),
            "tbr": f.get("tbr", 0),
            "fps": f.get("fps", 0) or 0,
            "resolution": f"{height}p" if height else "audio",
            "has_video": has_video,
            "has_audio": has_audio,
        }
        result["formats"].append(fmt)

    # Sort: formats with both audio+video first, then resolution, then size
    result["formats"].sort(key=lambda x: (x["has_video"] and x["has_audio"], x["has_video"], x["height"], x["filesize_mb"]), reverse=True)

    # Try to get file sizes for formats that don't have it
    for fmt in result["formats"]:
        if fmt["filesize_mb"] == 0:
            size = get_filesize_mb(fmt["url"])
            if size:
                fmt["filesize_mb"] = size
                fmt["filesize"] = int(size * 1024 * 1024)

    # Best single format (video+audio)
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

    if not re.match(r"https?://[^\s]+", url):
        return jsonify({"error": "Format URL tidak valid. Gunakan link yang lengkap (https://...)"}), 400

    try:
        result = extract_info(url)
        return jsonify(result)
    except Exception as e:
        err_msg = str(e)[:300]
        return jsonify({"error": err_msg}), 422


@app.route("/api/dl")
def api_download():
    """Proxy download: stream direct URL with Content-Disposition header."""
    dl_url = request.args.get("url", "")
    filename = request.args.get("filename", "donlotaja_video.mp4")

    if not dl_url:
        return jsonify({"error": "Missing url param"}), 400

    try:
        req = urllib.request.Request(dl_url)
        req.add_header("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")

        # Instagram CDN might need referrer
        if "instagram.com" in dl_url or "cdninstagram" in dl_url:
            req.add_header("Referer", "https://www.instagram.com/")

        resp = urllib.request.urlopen(req, timeout=30)

        def generate():
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                yield chunk

        return Response(
            generate(),
            status=resp.status,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": resp.headers.get("Content-Length", ""),
                "Access-Control-Allow-Origin": "*",
            }
        )
    except urllib.error.HTTPError as e:
        return jsonify({"error": f"HTTP {e.code}: {e.reason}"}), e.code
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 502


@app.route("/api/cookies-status")
def cookies_status():
    cookie_file = get_cookie_file()
    return jsonify({
        "has_cookies": cookie_file is not None,
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
