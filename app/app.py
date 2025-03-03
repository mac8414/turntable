from flask import Flask, render_template, jsonify, request
import random
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
import os

app = Flask(__name__)

client_credentials_manager = SpotifyClientCredentials(
    client_id=os.getenv('SPOTIPY_CLIENT_ID'),
    client_secret=os.getenv('SPOTIPY_CLIENT_SECRET')
)

spotify = Spotify(client_credentials_manager=client_credentials_manager)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')
@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/random_song')
def random_song():
    year = request.args.get('year')
    genre = request.args.get('genre')

    query_parts = []
    
    if year and year.lower() != "random year":
        query_parts.append(f"year:{year}")

    if genre and genre.lower() != "random genre":
        query_parts.append(f"genre:{genre}")
    else:
        # If only the year is given, append a common word to improve search results
        query_parts.append(random.choice(["music", "song", "love", "dance", "classic", "hit"]))

    query = " ".join(query_parts)

    try:
        results = spotify.search(q=query, type="track", limit=1, offset=random.randint(0, 50))

        if results.get('tracks', {}).get('items'):
            track = results['tracks']['items'][0]
            return jsonify(
                name=track.get('name', 'Unknown Song'),
                url=track.get('external_urls', {}).get('spotify', ''),
                image=track.get('album', {}).get('images', [{}])[0].get('url', None),
                artist=track.get('artists', [{}])[0].get('name', 'Unknown Artist'),
                type="song",
                preview_url=track.get('preview_url', None)
            )
    except Exception as e:
        return jsonify(error=str(e))

    return jsonify(name=None)

# FIX ME: The whole implementation of this does not work for a specific genre when you search.
# For whatever reason we are not able to get the genre of the album to work in the query.
@app.route('/random_album')
def random_album():
    year = request.args.get('year')
    genre = request.args.get('genre')

    query_parts = []
    if year and year != "Random Year":
        query_parts.append(f"year:{year}")
    if genre and genre != "Random Genre":
        query_parts.append(f"genre:{genre}")

    query = " ".join(query_parts) if query_parts else random.choice("abcdefghijklmnopqrstuvwxyz")

    results = spotify.search(q=query, type="album", limit=1, offset=random.randint(0, 50))

    if results['albums']['items']:
        album = results['albums']['items'][0]
        artist_id = album['artists'][0]['id']
    
        # Make an additional API call to get artist details (including genres)
        artist_info = spotify.artist(artist_id)
    
        # Get genres list (might be empty for some artists)
        genres = artist_info['genres']
        return jsonify(
            name=album['name'],
            url=album['external_urls']['spotify'],  # Link to album
            image=album['images'][0]['url'],  # Album image
            artist=album['artists'][0]['name'],
            type="album")
    else:
        return jsonify(name=None)

# FIX ME: NEEDS HELP. This feature doesn't work properly with the genre or the year. Needs to be fixed.
# Only generates a random artist, but doesn't take into account the genre or the year.
@app.route('/random_artist')
def random_artist():
    genre = request.args.get('genre')

    query_parts = []
    if genre and genre != "Random Genre":
        query_parts.append(f"genre:{genre}")

    query = " ".join(query_parts) if query_parts else random.choice("abcdefghijklmnopqrstuvwxyz")

    results = spotify.search(q=query, type="artist", limit=1, offset=random.randint(0, 50))
    # TODO: THIS IS WHERE THE PROBLEM IS. THE QUERY IS NOT WORKING PROPERLY.
    if results['artists']['items']:
        artist = results['artists']['items'][0]
        return jsonify(
            name=artist['name'],
            url=artist['external_urls']['spotify'],  # Link to artist page
            image=artist['images'][0]['url'] if artist['images'] else None,  # Artist image (if available)
            type="artist"
        )
    else:
        return jsonify(name=None)




if __name__ == "__main__":
    app.run(debug=True)