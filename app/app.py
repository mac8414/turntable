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

API_KEY = os.getenv("LASTFM_API_KEY")
BASE_URL = "http://ws.audioscrobbler.com/2.0/"

geniusToken = os.getenv('GENIUS_TOKEN')

genius = lyricsgenius.Genius(geniusToken)

sentiment_analyzer = pipeline("sentiment-analysis")

def get_recommendations(track_name, artist_name):
    recommendations = get_lastfm_similar_tracks(track_name, artist_name)
    
    if not recommendations:
        logger.info(f"No similar tracks from Last.fm for '{track_name}' by '{artist_name}', trying fallbacks")
        
        recommendations = get_artist_top_tracks(artist_name, original_track_name=track_name)
        
        if not recommendations:
            recommendations = get_genre_recommendations(track_name, artist_name)
            
        if not recommendations:
            recommendations = get_popular_tracks()
            
    return recommendations

def get_lastfm_similar_tracks(track_name, artist_name):
    params = {
        'method': 'track.getsimilar',
        'artist': artist_name,
        'track': track_name,
        'api_key': API_KEY,
        'format': 'json',
        'limit': 20
    }

    try:
        logger.info(f"Requesting similar tracks for '{track_name}' by '{artist_name}'")
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()  # Raise an error for HTTP issues
        data = response.json()
        
        # Log the entire response for debugging
        logger.debug(f"Last.fm API response: {data}")
        
        # More detailed error checking
        if 'error' in data:
            logger.warning(f"Last.fm API returned error: {data.get('message', 'Unknown error')}")
            return []
            
        if 'similartracks' not in data:
            logger.warning(f"Response missing 'similartracks' key for '{track_name}' by '{artist_name}'")
            return []
            
        if 'track' not in data['similartracks'] or not data['similartracks']['track']:
            logger.warning(f"No similar tracks found for '{track_name}' by '{artist_name}'")
            return []

        recommendations = []
        for track in data['similartracks']['track']:
            track_name = track.get('name', 'Unknown')
            artist_name = track.get('artist', {}).get('name', 'Unknown Artist')
            
            logger.debug(f"Found similar track: '{track_name}' by '{artist_name}'")
            
            try:
                spotify_results = spotify.search(q=f"{track_name} {artist_name}", type="track", limit=1)
                spotify_url = None
                if spotify_results.get('tracks', {}).get('items'):
                    spotify_url = spotify_results['tracks']['items'][0].get('external_urls', {}).get('spotify')
                    if spotify_url:
                        logger.debug(f"Found Spotify URL for '{track_name}': {spotify_url}")
                    else:
                        logger.debug(f"No Spotify URL found for '{track_name}' by '{artist_name}'")
                
                recommendations.append({
                    'name': track_name,
                    'artist': artist_name,
                    'spotify_url': spotify_url
                })
            except Exception as e:
                logger.warning(f"Error processing Spotify search for '{track_name}': {e}")
                # Still add the track even without Spotify URL
                recommendations.append({
                    'name': track_name,
                    'artist': artist_name,
                    'spotify_url': None
                })

        logger.info(f"Found {len(recommendations)} recommendations for '{track_name}' by '{artist_name}'")
        return recommendations
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP error fetching recommendations: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in get_recommendations: {str(e)}")
        return []

def get_artist_top_tracks(artist_name, original_track_name=None, limit=10):
    """Get top tracks from the same artist"""
    params = {
        'method': 'artist.getTopTracks',
        'artist': artist_name,
        'api_key': API_KEY,
        'format': 'json',
        'limit': limit
    }
    
    try:
        logger.info(f"Getting top tracks for artist: '{artist_name}'")
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'toptracks' not in data or 'track' not in data['toptracks']:
            logger.warning(f"No top tracks found for artist '{artist_name}'")
            return []
            
        recommendations = []
        for track in data['toptracks']['track']:
            # Skip the original track if a track name was provided
            if original_track_name and track.get('name') == original_track_name:
                continue
                
            spotify_results = spotify.search(q=f"{track['name']} {artist_name}", type="track", limit=1)
            spotify_url = None
            if spotify_results.get('tracks', {}).get('items'):
                spotify_url = spotify_results['tracks']['items'][0].get('external_urls', {}).get('spotify')
            
            recommendations.append({
                'name': track['name'],
                'artist': artist_name,
                'spotify_url': spotify_url
            })
                
        logger.info(f"Found {len(recommendations)} top tracks for artist '{artist_name}'")
        return recommendations
    except Exception as e:
        logger.error(f"Error getting artist top tracks: {e}")
        return []

def get_genre_recommendations(track_name, artist_name, limit=10):
    """Get recommendations based on genre/tags of the original track"""
    # First, get the tags for the track
    params = {
        'method': 'track.getInfo',
        'artist': artist_name,
        'track': track_name,
        'api_key': API_KEY,
        'format': 'json'
    }
    
    try:
        logger.info(f"Getting tags for '{track_name}' by '{artist_name}'")
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        tags = []
        if 'track' in data and 'toptags' in data['track'] and 'tag' in data['track']['toptags']:
            tags = [tag['name'] for tag in data['track']['toptags']['tag']]
        
        # If no tags, get artist tags instead
        if not tags:
            params = {
                'method': 'artist.getTopTags',
                'artist': artist_name,
                'api_key': API_KEY,
                'format': 'json'
            }
            response = requests.get(BASE_URL, params=params)
            data = response.json()
            
            if 'toptags' in data and 'tag' in data['toptags']:
                tags = [tag['name'] for tag in data['toptags']['tag']]
        
        if not tags:
            logger.warning(f"No tags found for '{track_name}' or artist '{artist_name}'")
            return []
            
        logger.info(f"Found tags: {tags}")
        
        # Now get tracks by tag (use the first/most relevant tag)
        if tags:
            params = {
                'method': 'tag.getTopTracks',
                'tag': tags[0],
                'api_key': API_KEY,
                'format': 'json',
                'limit': limit
            }
            
            response = requests.get(BASE_URL, params=params)
            data = response.json()
            
            if 'tracks' in data and 'track' in data['tracks']:
                recommendations = []
                for track in data['tracks']['track']:
                    # Skip if it's the original track or from the same artist
                    if track['name'] == track_name and track['artist']['name'] == artist_name:
                        continue
                        
                    spotify_results = spotify.search(q=f"{track['name']} {track['artist']['name']}", type="track", limit=1)
                    spotify_url = None
                    if spotify_results.get('tracks', {}).get('items'):
                        spotify_url = spotify_results['tracks']['items'][0].get('external_urls', {}).get('spotify')
                    
                    recommendations.append({
                        'name': track['name'],
                        'artist': track['artist']['name'],
                        'spotify_url': spotify_url
                    })
                
                logger.info(f"Found {len(recommendations)} recommendations by tag '{tags[0]}'")
                return recommendations
                
        return []
    except Exception as e:
        logger.error(f"Error getting genre recommendations: {e}")
        return []

def get_popular_tracks(limit=10):
    """Last resort: get overall popular tracks"""
    params = {
        'method': 'chart.getTopTracks',
        'api_key': API_KEY,
        'format': 'json',
        'limit': limit
    }
    
    try:
        logger.info("Getting popular tracks as last resort")
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'tracks' in data and 'track' in data['tracks']:
            recommendations = []
            for track in data['tracks']['track']:
                spotify_results = spotify.search(q=f"{track['name']} {track['artist']['name']}", type="track", limit=1)
                spotify_url = None
                if spotify_results.get('tracks', {}).get('items'):
                    spotify_url = spotify_results['tracks']['items'][0].get('external_urls', {}).get('spotify')
                
                recommendations.append({
                    'name': track['name'],
                    'artist': track['artist']['name'],
                    'spotify_url': spotify_url
                })
            
            logger.info(f"Found {len(recommendations)} popular tracks")
            return recommendations
        return []
    except Exception as e:
        logger.error(f"Error getting popular tracks: {e}")
        return []
    
def analyze_and_rank_recommendations(recommendations, original_track, original_artist):
    if not isinstance(recommendations, list):
        return "Invalid recommendations format"

    original_song = genius.search_song(original_track, original_artist)
    if not original_song or not original_song.lyrics:
        return "Original song lyrics not found"

    # Truncate lyrics to fit the model's maximum sequence length
    original_lyrics = original_song.lyrics[:512]
    original_sentiment = sentiment_analyzer(original_lyrics)[0]
    original_label = original_sentiment['label']  # Get the sentiment label (POSITIVE or NEGATIVE)
    print(f"Original Song Sentiment: {original_label} (Score: {original_sentiment['score']:.4f})")

    # Track already processed songs to avoid duplicates
    processed_tracks = set()
    scored_recommendations = []

    for track in recommendations:
        # Ensure the track has the required fields
        if not isinstance(track, dict) or 'name' not in track or 'artist' not in track:
            continue  # Skip malformed data

        artist = track['artist']
        name = track['name']
        
        # Skip the original song
        if name.lower() == original_track.lower() and artist.lower() == original_artist.lower():
            continue

        # Create a unique key for this track
        track_key = f"{name.lower()}|{artist.lower()}"
        
        # Skip if we've already processed this track
        if track_key in processed_tracks:
            continue
            
        processed_tracks.add(track_key)
        spotify_url = track.get('spotify_url')  # Handle missing Spotify URL gracefully

        try:
            song = genius.search_song(name, artist)
            if song and song.lyrics:
                # Truncate lyrics to fit the model's maximum sequence length
                lyrics = song.lyrics[:512]
                sentiment = sentiment_analyzer(lyrics)[0]
                current_label = sentiment['label']

                # Print sentiment stats for the current song
                print(f"Analyzing: {name} by {artist}")
                print(f"  Sentiment: {current_label} (Score: {sentiment['score']:.4f})")

                # Only consider songs with matching sentiment label (POSITIVE or NEGATIVE)
                if current_label == original_label:
                    similarity = abs(sentiment['score'] - original_sentiment['score'])

                    scored_recommendations.append({
                        'title': name,
                        'artist': artist,
                        'sentiment': sentiment,
                        'similarity': similarity,
                        'spotify_url': spotify_url  # Include Spotify URL
                    })
        except Exception as e:
            logger.error(f"Error analyzing song '{name}' by '{artist}': {e}")
            continue  # Skip errors gracefully

    # Sort by sentiment similarity (lower value = more similar)
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

@app.route('/randomizer')
def randomizer():
    logger.info("Rendering randomizer page")
    return render_template('randomizer.html')

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

@app.route('/spotify-search')
def spotify_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])

    try:
        results = spotify.search(q=query, type='track', limit=10)
        tracks = results.get('tracks', {}).get('items', [])
        return jsonify([
            {
                'id': track['id'],
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'image': track['album']['images'][1]['url'] if track['album']['images'] else ''
            } for track in tracks
        ])
    except Exception as e:
        logger.error(f"Spotify search error: {e}")
        return jsonify([])
    


@app.route('/submit-song', methods=['POST'])
def submit_song():
    data = request.get_json()
    track_name = data.get('track')
    artist_name = data.get('artist')

    if not track_name or not artist_name:
        return jsonify({'error': 'Missing track or artist'}), 400

    logger.info(f"Song selected: {track_name} by {artist_name}")

    # Get recommendations
    recommendations = get_recommendations(track_name, artist_name)
    ranked = analyze_and_rank_recommendations(recommendations, track_name, artist_name)

    return jsonify(ranked)


# Run the test
if __name__ == "__main__":
    test_recommendation_system()