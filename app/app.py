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

@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/random_album')
def random_album():
    year = request.args.get('year')
    genre = request.args.get('genre')
    if year is not None and year != "Random Year":
        query = f'year:{year}'
        results = spotify.search(q=query, type="album", limit=1, offset=random.randint(0, 50))
        
    else:
        random_letter = random.choice("abcdefghijklmnopqrstuvwxyz")
        results = spotify.search(q=random_letter, type="album", limit=1, offset=random.randint(0, 50))

    # Get album details
    if results['albums']['items']:
        album = results['albums']['items'][0]
        album_name = album['name']
        album_url = album['external_urls']['spotify']
        album_image = album['images'][0]['url']
        artist_name = album['artists'][0]['name']
        artist_id = album['artists'][0]['id']
        artist_info = spotify.artist(artist_id)
        genres = artist_info['genres']
        return jsonify(album_name=album_name, album_url=album_url, album_image=album_image, artist_name=artist_name, genres=genres)
    else:
        return jsonify(album_name=None)

if __name__ == "__main__":
    app.run(debug=True)