from flask import Flask, render_template, jsonify, request, redirect, url_for
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

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
        query_parts.append(random.choice(["music", "song", "love", "dance", "classic", "hit"]))

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
    year = request.args.get('year')
    genre = request.args.get('genre')
    logger.info(f"Random album request received with year: {year}, genre: {genre}")

    # Start with a basic query to get albums
    query_parts = []
    if year and year != "Random Year":
        query_parts.append(f"year:{year}")
    
    query = " ".join(query_parts) if query_parts else random.choice("abcdefghijklmnopqrstuvwxyz1234567890")

    offset = random.randint(0, 50)
    
    results = spotify.search(q=query, type="album", limit=50, offset=offset)
    
    filtered_albums = []
    
    if results['albums']['items']:
        for album in results['albums']['items']:
            if not genre or genre == "Random Genre":
                filtered_albums.append(album)
                continue
                
            artist_id = album['artists'][0]['id']
            artist_info = spotify.artist(artist_id)
            artist_genres = artist_info['genres']
            
            if any(genre.lower() in ag.lower() for ag in artist_genres):
                filtered_albums.append(album)

    if filtered_albums:
        random_album = random.choice(filtered_albums)
        image_url = random_album['images'][0]['url'] if random_album['images'] else None
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
        logger.info(f"Found album: {random_album['name']}")
        return jsonify(
            name=random_album['name'],
            url=random_album['external_urls']['spotify'],
            image=image_url,
            artist=random_album['artists'][0]['name'],
            type="album",
            dominant_color=dominant_color
        )
    else:
        logger.warning("No album found")
        return jsonify(name=None)

@app.route('/random_artist')
def random_artist():
    genre = request.args.get('genre')
    logger.info(f"Random artist request received with genre: {genre}")
    
    max_attempts = 10
    attempts = 0
    
    while attempts < max_attempts:
        attempts += 1
        
        if genre and genre.lower() != "random genre":
            query = f"genre:{genre}"
        else:
            query = random.choice("abcdefghijklmnopqrstuvwxyz1234567890")
        
        offset = random.randint(0, 100)
        results = spotify.search(q=query, type="artist", limit=50, offset=offset)
        
        if results['artists']['items']:
            random_index = random.randint(0, len(results['artists']['items']) - 1)
            artist = results['artists']['items'][random_index]
            image_url = artist['images'][0]['url'] if artist['images'] else None
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
            if genre and genre.lower() != "random genre":
                artist_id = artist['id']
                artist_info = spotify.artist(artist_id)
                artist_genres = [g.lower() for g in artist_info.get('genres', [])]
                
                if not any(genre.lower() in g for g in artist_genres):
                    logger.info(f"Genre {genre} not found for artist {artist['name']}, trying again")
                    continue  # Try again if genre doesn't match

            logger.info(f"Found artist: {artist['name']}")
            return jsonify(
                name=artist['name'],
                url=artist['external_urls']['spotify'],
                image=image_url,
                type="artist",
                dominant_color=dominant_color
            )

    logger.warning("No artist found after maximum attempts")
    return jsonify(name=None)

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
    return render_template('success.html')  # You can create this page for the success message.

@app.rout('/our-pick')
def our_pick():
    logger.info("Rendering our pick page")
    return "WIP"

if __name__ == "__main__":
    app.run(debug=True)