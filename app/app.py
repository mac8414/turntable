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
from flask_compress import Compress
from dotenv import load_dotenv
import lyricsgenius
from transformers import pipeline

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

geniusToken = os.getenv('GENIUS_TOKEN')

genius = lyricsgenius.Genius(geniusToken)

sentiment_analyzer = pipeline("sentiment-analysis")

def get_recommendations(track_name, artist_name):
    # Search for the original track
    results = spotify.search(q=f"track:{track_name} artist:{artist_name}", type="track", limit=1)
    
    if not results['tracks']['items']:
        return "Track not found"
    
    # Get original track info
    track = results['tracks']['items'][0]
    track_id = track['id']
    artist_id = track['artists'][0]['id']
    original_artist_name = track['artists'][0]['name']
    
    # Get release year from album
    album = track['album']
    release_date = album['release_date']
    release_year = int(release_date.split('-')[0])
    
    # Calculate decade range
    decade_start = (release_year // 10) * 10
    decade_end = decade_start + 9
    
    # Get ALL genres from artist data - not just the first one
    artist_data = spotify.artist(artist_id)
    original_genres = artist_data.get('genres', [])
    
    if not original_genres:
        return "Genre not found for the original artist"

    # Track processed artists to avoid duplicates
    similar_tracks = []
    included_artists = set([original_artist_name.lower()])
    
    # 1. First try to find artists with similar genres
    similar_artists = set()
    
    # For each of the original artist's genres, find related artists
    for genre in original_genres:
        # Search for artists with this genre
        try:
            # Format genre properly in search query (with quotes for exact matching)
            artist_results = spotify.search(q=f'genre:"{genre}"', type="artist", limit=20)
            
            if 'artists' in artist_results and 'items' in artist_results['artists']:
                for artist in artist_results['artists']['items']:
                    artist_name = artist['name'].lower()
                    if artist_name != original_artist_name.lower():
                        similar_artists.add(artist['id'])
        except Exception as e:
            logger.error(f"Error searching artists for genre '{genre}': {str(e)}")
            continue

    # 2. For each similar artist, get their top tracks
    for artist_id in list(similar_artists)[:10]:  # Limit to 10 artists for efficiency
        try:
            artist_data = spotify.artist(artist_id)
            artist_name = artist_data['name']
            
            if artist_name.lower() in included_artists:
                continue
                
            # Verify genre overlap with original artist
            artist_genres = artist_data.get('genres', [])
            
            # Check if there's at least one genre in common
            if not any(genre in artist_genres for genre in original_genres):
                continue
                
            # Search for tracks by this artist in the same decade
            track_results = spotify.search(
                q=f"artist:{artist_name} year:{decade_start}-{decade_end}", 
                type="track", 
                limit=5
            )
            
            if 'tracks' in track_results and 'items' in track_results['tracks']:
                for item in track_results['tracks']['items'][:2]:  # Take up to 2 tracks per artist
                    if item['id'] == track_id:
                        continue
                        
                    similar_tracks.append(item)
                    
                    if len(similar_tracks) >= 20:
                        break
                        
            included_artists.add(artist_name.lower())
                
        except Exception as e:
            logger.error(f"Error getting tracks for artist {artist_id}: {str(e)}")
            continue
            
        if len(similar_tracks) >= 20:
            break
    
    # 3. If we don't have enough tracks yet, try more generic decade+genre searches
    if len(similar_tracks) < 20:
        # Use original artist's top genres to find more tracks
        top_genres = original_genres[:3]  # Use top 3 genres
        
        for genre in top_genres:
            if len(similar_tracks) >= 20:
                break
                
            try:
                # Search for tracks with this genre in the same decade
                query = f'genre:"{genre}" year:{decade_start}-{decade_end}'
                track_results = spotify.search(q=query, type="track", limit=20)
                
                if 'tracks' in track_results and 'items' in track_results['tracks']:
                    for item in track_results['tracks']['items']:
                        if item['id'] == track_id:
                            continue
                            
                        current_artist_name = item['artists'][0]['name'].lower()
                        if current_artist_name in included_artists:
                            continue
                            
                        # Double-check genre match to avoid country songs for Drake, etc.
                        current_artist_id = item['artists'][0]['id']
                        current_artist_data = spotify.artist(current_artist_id)
                        current_genres = current_artist_data.get('genres', [])
                        
                        # Check for genre overlap
                        if not set(current_genres).intersection(set(original_genres)):
                            continue
                            
                        similar_tracks.append(item)
                        included_artists.add(current_artist_name)
                        
                        if len(similar_tracks) >= 20:
                            break
            except Exception as e:
                logger.error(f"Error with genre search '{genre}': {str(e)}")
                continue
    
    # 4. If still not enough, use decade-only search as last resort, but still filter by genre overlap
    if len(similar_tracks) < 20:
        try:
            decade_query = f"year:{decade_start}-{decade_end}"
            track_results = spotify.search(q=decade_query, type="track", limit=50)
            
            if 'tracks' in track_results and 'items' in track_results['tracks']:
                for item in track_results['tracks']['items']:
                    if item['id'] == track_id:
                        continue
                    
                    current_artist_name = item['artists'][0]['name'].lower()
                    if current_artist_name in included_artists:
                        continue
                    
                    # Strict genre validation
                    current_artist_id = item['artists'][0]['id']
                    current_artist_data = spotify.artist(current_artist_id)
                    current_genres = current_artist_data.get('genres', [])
                    
                    # Must have at least one overlapping genre
                    if not set(current_genres).intersection(set(original_genres)):
                        continue
                    
                    similar_tracks.append(item)
                    included_artists.add(current_artist_name)
                    
                    if len(similar_tracks) >= 20:
                        break
        except Exception as e:
            logger.error(f"Error with decade search: {str(e)}")
    
    return similar_tracks[:20]

def analyze_and_rank_recommendations(recommendations, original_track, original_artist):
    if not isinstance(recommendations, list):
        return "Invalid recommendations format"

    original_song = genius.search_song(original_track, original_artist)
    if not original_song or not original_song.lyrics:
        return "Original song lyrics not found"

    # Truncate lyrics to fit the model's maximum sequence length
    original_lyrics = original_song.lyrics[:512]
    original_sentiment = sentiment_analyzer(original_lyrics)[0]
    print(f"Original Song Sentiment: {original_sentiment['label']} (Score: {original_sentiment['score']:.4f})")

    scored_recommendations = []

    for track in recommendations:
        if not isinstance(track, dict) or 'name' not in track or 'artists' not in track:
            continue  # Skip malformed data

        artist = track['artists'][0]['name']
        name = track['name']

        try:
            song = genius.search_song(name, artist)
            if song and song.lyrics:
                # Truncate lyrics to fit the model's maximum sequence length
                lyrics = song.lyrics[:512]
                sentiment = sentiment_analyzer(lyrics)[0]

                # Print sentiment stats for the current song
                print(f"Analyzing: {name} by {artist}")
                print(f"  Sentiment: {sentiment['label']} (Score: {sentiment['score']:.4f})")

                similarity = abs(sentiment['score'] - original_sentiment['score'])

                scored_recommendations.append({
                    'title': name,
                    'artist': artist,
                    'sentiment': sentiment,
                    'similarity': similarity,
                    'spotify_url': track['external_urls']['spotify']
                })
        except Exception as e:
            logger.error(f"Error analyzing song '{name}' by '{artist}': {e}")
            continue  # Skip errors gracefully

    scored_recommendations.sort(key=lambda x: x['similarity'])

    return scored_recommendations[:5]

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
    album = get_album("Songs in the Key of Life")
    artist = get_artist("Stevie Wonder")
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

def reset_state():
    # Reset any global variables or caches used by get_recommendations
    pass

def test_recommendation_system():
    while True:
        print("\n" + "=" * 50)
        print("Enter the song and artist to test the recommendation system.")
        print("Type 'exit' to quit.")
        print("=" * 50)

        # Prompt user for song name and artist name
        track_name = input("Enter the song name: ").strip()
        if track_name.lower() == "exit":
            print("Exiting the test.")
            break

        artist_name = input("Enter the artist name: ").strip()
        if artist_name.lower() == "exit":
            print("Exiting the test.")
            break

        reset_state()  # Clear state before processing each case
        print("\n" + "=" * 50)
        print(f"TESTING: {track_name} by {artist_name}")
        print("=" * 50)

        try:
            # Get recommendations
            recommendations = get_recommendations(track_name, artist_name)
            if isinstance(recommendations, str):
                print(f"Error: {recommendations}")
                continue

            # Analyze and rank recommendations
            ranked_recommendations = analyze_and_rank_recommendations(
                recommendations, track_name, artist_name
            )

            if isinstance(ranked_recommendations, str):
                print(f"Error: {ranked_recommendations}")
                continue

            print("\nTOP 5 RECOMMENDATIONS (Ranked):")
            for i, rec in enumerate(ranked_recommendations):
                print(f"{i + 1}. {rec['title']} by {rec['artist']}")
                print(f"   Sentiment: {rec['sentiment']}")
                print(f"   Similarity Score: {rec['similarity']}")
                print(f"   Spotify URL: {rec['spotify_url']}")
                print()
        except Exception as e:
            print(f"Error processing test case: {str(e)}")
    print("\nTesting completed!")


# Run the test
if __name__ == "__main__":
    test_recommendation_system()