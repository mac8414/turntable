import os  # Import os for file deletion
import deezer
import librosa
import numpy as np
from transformers import pipeline

def get_song_preview(track_id):
    """
    Fetches the preview URL of a song from Deezer using the deezer-python library.
    :param track_id: The Deezer track ID.
    :return: The preview URL or None if not found.
    """
    client = deezer.Client()
    track = client.get_track(track_id)
    return track.preview  # Returns the preview URL

def download_audio(url, filename="preview.mp3"):
    import requests
    headers = {
        "User-Agent": "Mozilla/5.0",  # Pretend to be a browser
        "Referer": "https://www.deezer.com",  # Fake it came from Deezer
        "Range": "bytes=0-"  # Request whole file
    }

    response = requests.get(url, headers=headers, stream=True)
    if response.status_code in [200, 206]:  # 206 = Partial Content (normal for Range requests)
        with open(filename, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
        return filename
    else:
        print(f"Error downloading audio: {response.status_code} - {response.text}")
        return None

def extract_audio_features(audio_path):
    """
    Extracts audio features from the given audio file.
    :param audio_path: Path to the audio file.
    :return: Extracted features (e.g., MFCCs).
    """
    y, sr = librosa.load(audio_path, sr=None)
    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    return np.mean(mfccs.T, axis=0)

def analyze_audio_sentiment(features):
    """
    Analyzes the sentiment of the audio features.
    :param features: Extracted audio features.
    :return: Sentiment score and label.
    """
    sentiment_pipeline = pipeline("sentiment-analysis")
    # Convert features to a string representation (mock example)
    features_as_text = " ".join(map(str, features))
    result = sentiment_pipeline(features_as_text)
    return result[0]

def get_track_id_by_name(track_name, artist_name):
    """
    Searches for a track by name using the Deezer API and retrieves its track ID.
    :param track_name: The name of the track to search for.
    :return: The track ID or None if not found.
    """
    client = deezer.Client()
    results = client.search(track_name)  # Search for the track by name
    for track in results:
        if track.artist.name.lower() == artist_name.lower():
            return track.id
    else:
        print("Track not found.")
        return None

def get_artist_id_by_name(track_name, artist_name):
    client = deezer.Client()
    results = client.search(track_name)

    artist_id = None
    for track in results:
        if track.artist.name.lower() == artist_name.lower():
            artist_id = track.artist.id
            return artist_id
    else:
        print("Artist ID not found")
        return None

def get_artist_recommendations(track_name, artist_name, limit=5):  # Changed limit to 5
    client = deezer.Client()
    artist_id = get_artist_id_by_name(track_name, artist_name)
    
    if not artist_id:
        return []
    
    artist = client.get_artist(artist_id)

    # Fetch all top tracks
    top_tracks = artist.get_top()  # No limit argument here

    recommendations = set()  # Use a set to avoid duplicates
    
    # Manually limit the number of tracks
    for track in top_tracks[:limit]:
        recommendations.add(f"{track.title} by {track.artist.name}")

    return list(recommendations)

def get_similar_recommendations(track_name, artist_name, limit=15):  # Changed limit to 15
    client = deezer.Client()
    artist_id = get_artist_id_by_name(track_name, artist_name)

    if not artist_id:
        return []
    
    artist = client.get_artist(artist_id)
    related_artists = artist.get_related()

    recommendations = set()  # Use a set to avoid duplicates

    for related in related_artists:
        top_tracks = related.get_top()[:2]
        for track in top_tracks:
            recommendations.add(f"{track.title} by {track.artist.name}")
            if len(recommendations) >= limit:
                return list(recommendations)

    return list(recommendations)[:limit]

def analyze_each_track(track_name, artist_name):
    """
    Analyzes recommendations and returns the top 5 closest to the initial query.
    :param track_name: The name of the track.
    :param artist_name: The name of the artist.
    :return: A list of the top 5 closest recommendations.
    """
    # Get recommendations
    artists_recs = get_artist_recommendations(track_name, artist_name, limit=5)
    similar_recs = get_similar_recommendations(track_name, artist_name, limit=15)

    total_recs = artists_recs + similar_recs

    # Analyze each recommendation
    analyzed_recs = []
    for rec in total_recs:
        rec_track, rec_artist = rec.split(" by ")
        track_id = get_track_id_by_name(rec_track, rec_artist)

        if track_id:
            preview_url = get_song_preview(track_id)
            if preview_url:
                audio_path = download_audio(preview_url)
                if audio_path:
                    try:
                        features = extract_audio_features(audio_path)
                        sentiment = analyze_audio_sentiment(features)
                        analyzed_recs.append((rec, sentiment["score"]))
                    finally:
                        # Ensure the file is deleted even if an error occurs
                        if os.path.exists(audio_path):
                            os.remove(audio_path)

    # Sort recommendations by sentiment score (descending)
    analyzed_recs.sort(key=lambda x: x[1], reverse=True)

    # Return the top 5 recommendations
    return [rec[0] for rec in analyzed_recs[:5]]

def main():
    track_name = "Vine St."  # Replace with the name of the song
    artist_name = "Bryce Vine"

    # Analyze recommendations and get the top 5
    results = analyze_each_track(track_name, artist_name)

    # Display the results
    print("Top 5 Recommendations Based on Sentiment Analysis:")
    for i, rec in enumerate(results, start=1):
        print(f"{i}. {rec}")

if __name__ == "__main__":
    main()