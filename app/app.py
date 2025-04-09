from flask import Flask, flash, render_template, jsonify, request, redirect, url_for
import random
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
import os
import requests
from io import BytesIO
from PIL import Image
from colorthief import ColorThief
from flask_mail import Mail, Message
import logging
import traceback
from flask_compress import Compress
from dotenv import load_dotenv

load_dotenv() 

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
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

client_credentials_manager = SpotifyClientCredentials(
    client_id=os.getenv('SPOTIPY_CLIENT_ID'),
    client_secret=os.getenv('SPOTIPY_CLIENT_SECRET')
)

spotify = Spotify(client_credentials_manager=client_credentials_manager)

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
    return render_template('contact.html')

@app.route('/home')
def home():
    logger.info("Rendering home page")
    return render_template('home.html')

@app.route('/random_song')
def random_song():
    year = request.args.get('year')
    genre = request.args.get('genre')
    logger.info(f"Random song request received with year: {year}, genre: {genre}")

    query_parts = []
    
    if year and year.lower() != "random year":
        query_parts.append(f"year:{year}")

    if genre and genre.lower() != "random genre":
        genre = genre.lower()
        query_parts.append(f"genre:{genre}")
    else:
        # If only the year is given, append a common word to improve search results
        query_parts.append(random.choice([ "Love", "You", "Me", "I", "My", "Baby", "Heart", "Night", "Time", "Day",
                                            "We", "Girl", "Boy", "Dream", "Dance", "Rain", "World", "Feel", "Life", "Way"]))

    query = " ".join(query_parts)
    max_attempts = 10
    attempts = 0
    
    while attempts < max_attempts:
        attempts += 1
        logger.info(f"Attempt {attempts} to find a random song with query: {query}")
        results = spotify.search(q=query, type="track", limit=1, offset=random.randint(0, 50))

        if results.get('tracks', {}).get('items'):
            track = results['tracks']['items'][0]
            image_url = track.get('album', {}).get('images', [{}])[0].get('url', None)
            dominant_color = "#000000"  # Default to black
            if image_url:
                try:
                    response = requests.get(image_url)
                    image = Image.open(BytesIO(response.content))
                    color_thief = ColorThief(BytesIO(response.content))
                    dominant_color_rgb = color_thief.get_color(quality=10)
                    dominant_color = f"#{dominant_color_rgb[0]:02x}{dominant_color_rgb[1]:02x}{dominant_color_rgb[2]:02x}"
                except Exception as e:
                    logger.error(f"Error extracting color: {e}")

            logger.info(f"Found song: {track.get('name', 'Unknown Song')}")
            return jsonify(
                name=track.get('name', 'Unknown Song'),
                url=track.get('external_urls', {}).get('spotify', ''),
                image=image_url,
                artist=track.get('artists', [{}])[0].get('name', 'Unknown Artist'),
                type="song",
                preview_url=track.get('preview_url', None),
                dominant_color=dominant_color
            )

    logger.warning("No song found after maximum attempts")
    return jsonify(name=None)

@app.route('/random_album')
def random_album():
    """Fetch a random album from Spotify with optional year and genre filters."""
    year = request.args.get('year')
    genre = request.args.get('genre')
    logger.info(f"Random album request received with year: {year}, genre: {genre}")

    try:
        if year and year != "Random Year":
            query = f"year:{year}"
        else:
            search_options = "abcdefghijklmnopqrstuvwxyz0123456789"
            query = random.choice(search_options)
        
        offset = random.randint(0, 200)
        
        results = spotify.search(q=query, type="album", limit=50, offset=offset)
        albums = results['albums']['items']
        
        filtered_albums = []
        artist_genre_cache = {}
        
        if albums:
            for album in albums:
                if not genre or genre == "":
                    filtered_albums.append(album)
                    continue
                    
                artist_id = album['artists'][0]['id']
                if artist_id in artist_genre_cache:
                    artist_genres = artist_genre_cache[artist_id]
                else:
                    try:
                        artist_info = spotify.artist(artist_id)
                        artist_genres = [g.lower() for g in artist_info['genres']]
                        artist_genre_cache[artist_id] = artist_genres
                    except Exception as e:
                        logger.warning(f"Error fetching artist genres: {str(e)}")
                        continue

                genre_lower = genre.lower()
                genre_words = genre_lower.replace('-', ' ').split()
                
                if any(genre_lower in ag for ag in artist_genres) or \
                   any(any(word in ag for word in genre_words if len(word) > 3) for ag in artist_genres):
                    filtered_albums.append(album)

        if filtered_albums:
            random_album = random.choice(filtered_albums)
            image_url = random_album['images'][0]['url'] if random_album['images'] else None
            dominant_color = "#000000"  # Default to black
            
            if image_url:
                try:
                    # Set timeout to avoid hanging
                    response = requests.get(image_url, timeout=3)
                    image_data = BytesIO(response.content)
                    
                    # Open with context manager for proper cleanup
                    with Image.open(image_data) as image:
                        # Resize for faster processing
                        image.thumbnail((100, 100))
                        color_thief = ColorThief(BytesIO(response.content))
                        dominant_color_rgb = color_thief.get_color(quality=5)
                        dominant_color = f"#{dominant_color_rgb[0]:02x}{dominant_color_rgb[1]:02x}{dominant_color_rgb[2]:02x}"
                except Exception as e:
                    logger.error(f"Error extracting color: {str(e)}")
            
            logger.info(f"Found album: {random_album['name']} by {random_album['artists'][0]['name']}")
            return jsonify(
                name=random_album['name'],
                url=random_album['external_urls']['spotify'],
                image=image_url,
                artist=random_album['artists'][0]['name'],
                type="album",
                dominant_color=dominant_color,
                release_date=random_album.get('release_date'),
                total_tracks=random_album.get('total_tracks')
            )
        else:
            logger.warning("No matching albums found")
            return jsonify(name=None, error="No matching albums found")
            
    except Exception as e:
        logger.error(f"Error in random_album: {str(e)}", exc_info=True)
        return jsonify(name=None, error="An error occurred while fetching albums"), 500

@app.route('/random_artist')
def random_artist():
    genre = request.args.get('genre')
    logger.info(f"Random artist request received with genre: {genre}")
    
    max_attempts = 10
    attempts = 0
    
    # More comprehensive character set for better diversity
    query_chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    
    # Pre-define wildcards to improve search effectiveness
    wildcards = ["%", "*", "", ""]  # Empty strings increase chance of regular character
    
    while attempts < max_attempts:
        attempts += 1
        
        # Create more effective random query
        query_char = random.choice(query_chars)
        wildcard = random.choice(wildcards)
        query = f"{wildcard}{query_char}{wildcard}"
        
        offset = random.randint(0, 950)  # Spotify allows up to 1000 in pagination
        
        try:
            results = spotify.search(q=query, type="artist", limit=50, offset=offset)
            
            artists = results['artists']['items']
            if not artists:
                logger.info(f"No results for query '{query}' with offset {offset}, trying again")
                continue
                
            if genre and genre.lower() != "random genre":
                matching_artists = []
                for artist in artists:
                    artist_id = artist['id']
                    try:
                        artist_info = spotify.artist(artist_id)
                        artist_genres = [g.lower() for g in artist_info.get('genres', [])]
                        
                        # More flexible genre matching - partial match or exact match
                        if any(genre.lower() in g for g in artist_genres) or any(g == genre.lower() for g in artist_genres):
                            matching_artists.append(artist)
                    except Exception as e:
                        logger.warning(f"Error fetching artist info for {artist['name']}: {e}")
                        continue
                
                if matching_artists:
                    artist = random.choice(matching_artists)
                else:
                    logger.info(f"No artists matching genre '{genre}' found in this batch, trying again")
                    continue
            else:
                artist = random.choice(artists)
            
            # Get image and dominant color
            image_url = None
            dominant_color = "#000000"  # Default to black
            
            if artist['images']:
                # Choose the medium-sized image if available for better performance
                if len(artist['images']) > 1:
                    image_url = artist['images'][1]['url']
                else:
                    image_url = artist['images'][0]['url']
                
                if image_url:
                    try:
                        response = requests.get(image_url, timeout=3)  # Add timeout
                        if response.status_code == 200:
                            color_thief = ColorThief(BytesIO(response.content))
                            dominant_color_rgb = color_thief.get_color(quality=10)
                            dominant_color = f"#{dominant_color_rgb[0]:02x}{dominant_color_rgb[1]:02x}{dominant_color_rgb[2]:02x}"
                    except Exception as e:
                        logger.error(f"Error extracting color for {artist['name']}: {e}")
            
            logger.info(f"Found artist: {artist['name']}, genre: {genre or 'any'}")
            return jsonify(
                name=artist['name'],
                url=artist['external_urls'].get('spotify', ''),
                image=image_url,
                type="artist",
                dominant_color=dominant_color,
                genres=artist.get('genres', [])  # Added genres to response
            )
            
        except Exception as e:
            logger.error(f"Error during Spotify search (attempt {attempts}): {e}")
    
    logger.warning(f"No suitable artist found after {max_attempts} attempts")
    return jsonify(
        name=None,
        error=f"No artist found matching criteria after {max_attempts} attempts"
    ), 404

# Route for Contact Form Page
@app.route('/contact-help', methods=['GET', 'POST'])
def contact_help():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        logger.info(f"Contact form submitted by {name} ({email})")

        # Create the email message
        msg = Message(f'New message from {name} ({email})',
                      recipients=['turntablehelp@gmail.com'])  
        msg.body = f'Name: {name}\nEmail: {email}\n\nMessage:\n{message}'

        try:
            mail.send(msg)
            logger.info("Email sent successfully")
            return redirect(url_for('success'))  # Redirect to success page
        except Exception as e:
            logger.error("Error sending email", exc_info=True)
            return 'An error occurred while sending your message. Please try again.'

    return render_template('contact.html')

# Route for Success Page
@app.route('/success')
def success():
    logger.info("Rendering success page")
    return render_template('success.html')  

@app.route('/our-pick')
def our_pick():
    logger.info("Rendering our pick page")
    album = get_album("What's Going On")
    artist = get_artist("Marvin Gaye")
    return render_template('our-pick.html', album=album, artist=artist)

def get_album(album_name):
    results = spotify.search(q=album_name, type="album", limit=1)
    items = results.get("albums", {}).get("items", [])

    if not items:
        return None

    album = items[0]  # First search result
    return {
        "name": album["name"],
        "image_url": album["images"][0]["url"],
        "spotify_url": album["external_urls"]["spotify"]
    }

def get_artist(artist_name):
    results = spotify.search(q=artist_name, type="artist", limit=1)
    items = results.get("artists", {}).get("items", [])

    if not items:
        return None

    artist = items[0]  # First search result
    return {
        "name": artist["name"],
        "image_url": artist["images"][0]["url"],
        "spotify_url": artist["external_urls"]["spotify"]
    }

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



if __name__ == "__main__":
    app.run(debug=True)