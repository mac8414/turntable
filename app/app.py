from flask import Flask, flash, render_template, jsonify, request, redirect, url_for
import os
import requests
from flask_mail import Mail, Message
import logging
import deezer
import crud
from crud import MusicRecommender
from flask_compress import Compress
import urllib.parse
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
Compress(app)

# Configuring Flask-Mail with Gmail SMTP
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'turntablehelp@gmail.com' 
app.config['MAIL_PASSWORD'] = 'fnuj qfow rnlt yaym'  
app.config['MAIL_DEFAULT_SENDER'] = 'turntablehelp@gmail.com'

mail = Mail(app)

RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")

# Last.fm API configuration
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")  # You'll need to set this environment variable
LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"

@app.route('/')
def index():
    logger.info("Redirecting to /home")
    return redirect('/home')

@app.route('/about')
def about():
    logger.info("Rendering about page")
    return render_template('about.html')

@app.route('/contact')
def contact():
    logger.info("Rendering contact page")
    return render_template('contact.html', recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/home')
def home():
    logger.info("Rendering home page")
    return render_template('home.html')

# Route for Success Page
@app.route('/success')
def success():
    logger.info("Rendering success page")
    return render_template('success.html')  

@app.route("/contact-help", methods=["POST"])
def contact_help():
    name = request.form.get("name")
    email = request.form.get("email")
    message = request.form.get("message")
    recaptcha_response = request.form.get("g-recaptcha-response")

    if not name or not email or not message:
        flash("All fields are required.", "error")
        return redirect(url_for("contact"))

    if not recaptcha_response:
        flash("Please complete the CAPTCHA.", "error")
        return redirect(url_for("contact"))

    verify_url = "https://www.google.com/recaptcha/api/siteverify"
    payload = {
        "secret": RECAPTCHA_SECRET_KEY,
        "response": recaptcha_response
    }

    try:
        r = requests.post(verify_url, data=payload)
        result = r.json()
        if not result.get("success"):
            flash("CAPTCHA failed. Please try again.", "error")
            return redirect(url_for("contact"))
    except Exception:
        flash("CAPTCHA validation error.", "error")
        return redirect(url_for("contact"))

    try:
        msg = Message(
            subject="New Contact Message",
            sender=email,
            recipients=["turntablehelp@gmail.com"],
            body=f"From: {name}\nEmail: {email}\n\nMessage:\n{message}"
        )
        mail.send(msg)
        flash("Message sent successfully!", "success")
        return redirect(url_for("success"))
    except Exception as e:
        logger.error(f"Email sending failed: {e}")
        flash("There was an error sending your message. Please try again.", "error")
        return redirect(url_for("contact"))

@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.get_json()
    query = data.get('query')

    if not query:
        return jsonify({"error": "No query provided"}), 400

    client = deezer.Client()
    try:
        results = client.search(query)
        tracks = [
            {
                "title": track.title,
                "artist": track.artist.name,
                "album_cover": track.album.cover_medium 
            }
            for track in results
        ]
        return jsonify({"results": tracks})
    except Exception as e:
        logger.error(f"API search failed: {e}")
        return jsonify({"error": "Search failed"}), 500

@app.route('/api/artist-info', methods=['POST'])
def get_artist_info():
    """
    Fetch artist information from Last.fm API
    """
    data = request.get_json()
    artist_name = data.get('artist_name')

    if not artist_name:
        return jsonify({"error": "No artist name provided"}), 400

    if not LASTFM_API_KEY:
        logger.warning("Last.fm API key not configured")
        return jsonify({"error": "Last.fm API not configured"}), 500

    try:
        # Make request to Last.fm API
        params = {
            'method': 'artist.getinfo',
            'artist': artist_name,
            'api_key': LASTFM_API_KEY,
            'format': 'json'
        }
        
        response = requests.get(LASTFM_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if 'error' in data:
            logger.error(f"Last.fm API error: {data.get('message', 'Unknown error')}")
            return jsonify({"error": "Artist not found"}), 404
        
        if 'artist' in data and data['artist'].get('bio') and data['artist']['bio'].get('summary'):
            bio = data['artist']['bio']['summary']
            
            # Clean up the bio text
            # Remove HTML tags
            bio = re.sub(r'<[^>]*>', '', bio)
            
            # Remove "Read more on Last.fm" and similar text
            bio = re.sub(r'Read more on Last\.fm.*$', '', bio, flags=re.IGNORECASE)
            bio = re.sub(r'User-contributed text is available under.*$', '', bio, flags=re.IGNORECASE)
            
            # Clean up extra whitespace
            bio = bio.strip()
            
            # Limit to first 2-3 sentences for brevity
            sentences = re.split(r'[.!?]+', bio)
            short_bio = '. '.join(sentences[:2]).strip()
            
            if short_bio and not short_bio.endswith('.'):
                short_bio += '.'
            
            # Get additional info if available
            artist_info = {
                'bio': short_bio if short_bio else None,
                'listeners': data['artist'].get('stats', {}).get('listeners'),
                'playcount': data['artist'].get('stats', {}).get('playcount'),
                'url': data['artist'].get('url'),
                'image': None
            }
            
            # Get artist image if available
            if 'image' in data['artist'] and data['artist']['image']:
                for img in data['artist']['image']:
                    if img.get('size') == 'large' and img.get('#text'):
                        artist_info['image'] = img['#text']
                        break
            
            return jsonify({"artist_info": artist_info})
        else:
            return jsonify({"error": "No artist information available"}), 404
            
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
    data = request.get_json()
    track_name = data.get('track_name')
    artist_name = data.get('artist_name')
    recommendations_count = data.get('count')

    if not track_name or not artist_name:
        return jsonify({"error": "Missing track or artist name"}), 400

    # Convert to int and provide a default if needed
    try:
        recommendations_count = int(recommendations_count)
    except (TypeError, ValueError):
        recommendations_count = 5  # or whatever default you want

    try:
        recommender = MusicRecommender()
        recommendations = recommender.get_recommendations(track_name, artist_name, recommendations_count)

        recommendations.sort(key=lambda x: x.similarity_score, reverse=True)

        results = []
        for track in recommendations:
            album_cover = get_album_cover_from_deezer(track.title, track.artist_name)
            
            results.append({
                "title": track.title,
                "artist": track.artist_name,
                "similarity_score": round(track.similarity_score * 100, 2),
                "album_cover": album_cover
            })

        return jsonify({"recommendations": results})

    except Exception as e:
        logger.error(f"Recommendation error: {e}")
        return jsonify({"error": "Recommendation failed"}), 500

def get_album_cover_from_deezer(title, artist):
    try:
        import requests
        import urllib.parse
        
        # Create search query
        query = urllib.parse.quote(f"{artist} {title}")
        url = f"https://api.deezer.com/search?q={query}&limit=1"
        
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data.get('data') and len(data['data']) > 0:
            track_data = data['data'][0]
            # Return medium size cover (250x250), fallback to other sizes
            return (track_data.get('album', {}).get('cover_medium') or 
                   track_data.get('album', {}).get('cover') or 
                   track_data.get('album', {}).get('cover_small'))
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching album cover for {title} by {artist}: {e}")
        return None

# Helper function to get artist information (can be used by other parts of your app)
def get_artist_info_helper(artist_name):
    """
    Helper function to get artist info that can be used elsewhere in the app
    """
    if not LASTFM_API_KEY or not artist_name:
        return None
    
    try:
        params = {
            'method': 'artist.getinfo',
            'artist': artist_name,
            'api_key': LASTFM_API_KEY,
            'format': 'json'
        }
        
        response = requests.get(LASTFM_BASE_URL, params=params, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        
        if 'artist' in data and data['artist'].get('bio') and data['artist']['bio'].get('summary'):
            bio = data['artist']['bio']['summary']
            
            # Clean up the bio text
            bio = re.sub(r'<[^>]*>', '', bio)
            bio = re.sub(r'Read more on Last\.fm.*$', '', bio, flags=re.IGNORECASE)
            bio = bio.strip()
            
            # Limit to first 2 sentences
            sentences = re.split(r'[.!?]+', bio)
            short_bio = '. '.join(sentences[:2]).strip()
            
            if short_bio and not short_bio.endswith('.'):
                short_bio += '.'
                
            return short_bio
            
    except Exception as e:
        logger.error(f"Error fetching artist info for {artist_name}: {e}")
        
    return None

# # Run the test    
if __name__ == "__main__":
     app.run(debug=True)