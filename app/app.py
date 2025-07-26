from flask import Flask, flash, render_template, jsonify, request, redirect, url_for
import os
import requests
from flask_mail import Mail, Message
import logging
import deezer
import crud
from crud import MusicRecommender
from flask_compress import Compress
import time

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

@app.route('/our-pick')
def our_pick():
    logger.info("Rendering our pick page")
    album = get_album("Songs in the Key of Life")
    artist = get_artist("Stevie Wonder")
    return render_template('our-pick.html', album=album, artist=artist)

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
        # Measure time for get_recommendations
        start_time = time.time()
        recommendations = recommender.get_recommendations(track_name, artist_name, recommendations_count)
        elapsed_time = time.time() - start_time
        logger.info(f"get_recommendations for '{track_name}' by '{artist_name}' took {elapsed_time:.2f} seconds")

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

# # Run the test    
if __name__ == "__main__":
     app.run(debug=True)
