from flask import Flask, flash, render_template, jsonify, request, redirect, url_for
import os
import requests
from flask_mail import Mail, Message
import logging
from crud import MusicRecommender, MAX_RECOMMENDATIONS_COUNT, FINAL_RECOMMENDATIONS_COUNT, display_title
from flask_compress import Compress
import re
from dotenv import load_dotenv
import traceback
import time

load_dotenv()  # Load environment variables from .env file

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(32)
Compress(app)

RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")

# Last.fm API configuration
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"

MAX_SEARCH_RESULTS = 50

# Shared so the Deezer/Last.fm/audio caches and rate limiter persist across requests
recommender = MusicRecommender()


@app.route('/')
def index():
    return redirect('/home')

@app.route('/about')
def about():
    return render_template('about.html', recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/contact')
def contact():
    return redirect(url_for('about', _anchor='contact'))

@app.route('/home')
def home():
    return render_template('home.html')

# Route for Success Page
@app.route('/success')
def success():
    return render_template('success.html')

@app.route("/contact-help", methods=["POST"])
def contact_help():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    message = request.form.get("message", "").strip()
    recaptcha_response = request.form.get("g-recaptcha-response")
    back_to_form = redirect(url_for("about", _anchor="contact"))

    if not name or not email or not message:
        flash("All fields are required.", "error")
        return back_to_form

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        flash("Please enter a valid email address.", "error")
        return back_to_form

    if not recaptcha_response:
        flash("Please complete the CAPTCHA.", "error")
        return back_to_form

    try:
        r = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": RECAPTCHA_SECRET_KEY, "response": recaptcha_response},
            timeout=10
        )
        if not r.json().get("success"):
            flash("CAPTCHA failed. Please try again.", "error")
            return back_to_form
    except Exception:
        flash("CAPTCHA validation error.", "error")
        return back_to_form

    try:
        # Gmail only sends as the authenticated account, so put the visitor in Reply-To
        msg = Message(
            subject=f"New Contact Message from {name}",
            recipients=[CONTACT_EMAIL],
            reply_to=email,
            body=f"From: {name}\nEmail: {email}\n\nMessage:\n{message}"
        )
        mail.send(msg)
        return redirect(url_for("success"))
    except Exception as e:
        logger.error(f"Email sending failed: {e}")
        flash("There was an error sending your message. Please try again.", "error")
        return back_to_form

@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.get_json(silent=True) or {}
    query = str(data.get('query') or '').strip()

    if not query:
        return jsonify({"error": "No query provided"}), 400

    try:
        limit = max(1, min(int(data.get('limit', 20)), MAX_SEARCH_RESULTS))
    except (TypeError, ValueError):
        limit = 20

    try:
        results = recommender.deezer_client.search(query, limit)
        tracks = [
            {
                "id": track.id,
                "title": track.title,
                "artist": track.artist.name,
                "album": track.album.title,
                "album_cover": track.album.cover_medium
            }
            for track in results
        ]
        return jsonify({"results": tracks})
    except Exception as e:
        logger.error(f"API search failed: {e}")
        return jsonify({"error": "Search failed"}), 500

def _clean_bio(bio: str) -> str:
    """Strip Last.fm markup/boilerplate and keep the first two sentences."""
    bio = re.sub(r'<[^>]*>', '', bio)
    bio = re.sub(r'Read more on Last\.fm.*$', '', bio, flags=re.IGNORECASE | re.DOTALL)
    bio = re.sub(r'User-contributed text is available under.*$', '', bio, flags=re.IGNORECASE | re.DOTALL)
    bio = re.sub(r'\s+', ' ', bio).strip()
    # Split on sentence ends followed by a capital letter so "Mr. Smith" or "U.S." don't split
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', bio)
    return ' '.join(sentences[:2]).strip()

@app.route('/api/artist-info', methods=['POST'])
def get_artist_info():
    """
    Fetch artist information from Last.fm API
    """
    data = request.get_json(silent=True) or {}
    artist_name = str(data.get('artist_name') or '').strip()

    if not artist_name:
        return jsonify({"error": "No artist name provided"}), 400

    if not LASTFM_API_KEY:
        logger.warning("Last.fm API key not configured")
        return jsonify({"error": "Last.fm API not configured"}), 500

    try:
        params = {
            'method': 'artist.getinfo',
            'artist': artist_name,
            'api_key': LASTFM_API_KEY,
            'format': 'json',
            'autocorrect': 1
        }
        response = requests.get(LASTFM_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if 'error' in data or 'artist' not in data:
            return jsonify({"error": "Artist not found"}), 404

        artist = data['artist']
        bio = _clean_bio(artist.get('bio', {}).get('summary') or '')
        artist_info = {
            'bio': bio or None,
            'listeners': artist.get('stats', {}).get('listeners'),
            'playcount': artist.get('stats', {}).get('playcount'),
            'tags': [t.get('name') for t in artist.get('tags', {}).get('tag', [])][:3],
            'url': artist.get('url'),
        }
        return jsonify({"artist_info": artist_info})

    except requests.exceptions.Timeout:
        logger.error(f"Last.fm API timeout for artist: {artist_name}")
        return jsonify({"error": "Request timeout"}), 504
    except requests.exceptions.RequestException as e:
        logger.error(f"Last.fm API request failed for artist {artist_name}: {e}")
        return jsonify({"error": "External API error"}), 503
    except Exception as e:
        logger.error(f"Unexpected error fetching artist info for {artist_name}: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/recommend', methods=['POST'])
def recommend():
    data = request.get_json(silent=True) or {}
    track_name = str(data.get('track_name') or '').strip()
    artist_name = str(data.get('artist_name') or '').strip()

    if not track_name or not artist_name:
        return jsonify({"error": "Missing track or artist name"}), 400

    try:
        recommendations_count = max(1, min(int(data.get('count')), MAX_RECOMMENDATIONS_COUNT))
    except (TypeError, ValueError):
        recommendations_count = FINAL_RECOMMENDATIONS_COUNT

    start_time = time.time()
    try:
        logger.info(f"Starting recommendation for: {track_name} by {artist_name}")
        result = recommender.get_recommendations(
            track_name, artist_name, recommendations_count,
            genre=data.get('genre') or None,
            timeframe=data.get('timeframe') or None,
            track_id=data.get('track_id') or None,
        )
        logger.info(f"Recommendation completed in {time.time() - start_time:.2f} seconds")

        results = [
            {
                "title": display_title(track.title),
                "artist": track.artist_name,
                "similarity_score": round(track.similarity_score * 100),
                "album_cover": track.album_cover,
                "release_year": track.release_year,
            }
            for track in result.tracks
        ]
        return jsonify({"recommendations": results, "notices": result.notices})

    except Exception:
        logger.error(f"Recommendation error after {time.time() - start_time:.2f}s: %s", traceback.format_exc())
        return jsonify({"error": "Recommendation failed. Please try again."}), 500

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
