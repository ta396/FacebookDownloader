"""
FB Video Downloader - Backend
Uses yt-dlp to extract direct video URLs from Facebook, serves them
to the HTML frontend via a small Flask API.

Run:
    pip install -r requirements.txt
    python app.py
Then open fb-video-downloader.html in your browser.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from yt_dlp import YoutubeDL
import re

app = Flask(__name__)
CORS(app)  # allow the HTML file (opened locally) to call this API


def is_facebook_url(url: str) -> bool:
    return bool(re.match(
        r"^https?://(www\.|web\.|m\.|mbasic\.)?(facebook|fb)\.com/",
        url.strip(), re.I
    ))


@app.route("/api/fetch")
def fetch():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "Missing url parameter"}), 400
    if not is_facebook_url(url):
        return jsonify({"error": "Not a Facebook URL"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        # Some public FB videos work without cookies.
        # For private/age-restricted videos you may need to add:
        # "cookiesfrombrowser": ("chrome",),
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title") or "Untitled"
        # Facebook often returns no thumbnail; fall back to info-level url
        thumbnail = info.get("thumbnail") or ""
        if not thumbnail and info.get("thumbnails"):
            thumbnail = info["thumbnails"][-1].get("url", "")
        uploader = info.get("uploader") or info.get("channel") or "Unknown"
        duration = info.get("duration") or 0
        m, s = divmod(int(duration), 60)
        duration_str = f"{m}:{s:02d}" if duration else "—"

        formats = []
        seen = set()

        # Facebook's yt-dlp extractor returns progressive mp4 formats with
        # format_id like "sd"/"hd" and vcodec/acodec left as None (not "none").
        # So we relax the filter: any mp4 with a url counts as a usable stream.
        for f in info.get("formats", []):
            ext = f.get("ext", "")
            url_f = f.get("url")
            if ext != "mp4" or not url_f:
                continue
            fid = (f.get("format_id") or "").lower()
            note = (f.get("format_note") or "").lower()
            height = f.get("height") or 0

            # Build a readable quality label
            if fid == "hd" or "hd" in note or height >= 720:
                label = f"HD {height}p" if height else "HD"
            elif fid == "sd" or height:
                label = f"SD {height}p" if height else "SD"
            else:
                label = fid.upper() if fid else "MP4"

            if label in seen:
                continue
            seen.add(label)
            formats.append({
                "quality": label,
                "type": "video",
                "url": url_f,
                "_height": height if height else (9999 if "hd" in label else 0),
            })

        # Sort by quality (HD first), keep top 3
        formats.sort(key=lambda x: x.get("_height", 0), reverse=True)
        video_formats = formats[:3]
        for f in video_formats:
            f.pop("_height", None)

        # Best-effort audio-only extraction
        audio_url = None
        for f in info.get("formats", []):
            acodec = f.get("acodec")
            if acodec and acodec != "none" and (f.get("vcodec") in (None, "none")) and f.get("url"):
                audio_url = f["url"]
                break
        if audio_url:
            video_formats.append({
                "quality": "Audio MP3",
                "type": "audio",
                "url": audio_url,
            })

        # Fallback: if formats list was empty but info-level url exists (HD progressive)
        if not video_formats and info.get("url"):
            video_formats.append({
                "quality": "HD",
                "type": "video",
                "url": info["url"],
            })

        if not video_formats:
            return jsonify({
                "error": "No downloadable formats found. The video may be private, age-restricted, or require login."
            }), 422

        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "author": uploader,
            "duration": duration_str,
            "formats": video_formats,
        })

    except Exception as e:
        msg = str(e)
        # yt-dlp often raises on private / login-required videos
        return jsonify({
            "error": f"Could not extract video: {msg}"
        }), 500


@app.route("/api/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("FB Video Downloader backend running on http://localhost:5000")
    print("Open fb-video-downloader.html in your browser.")
    app.run(host="127.0.0.1", port=5000, debug=False)
