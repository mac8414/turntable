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

def get_track_id_by_name(track_name):
    """
    Searches for a track by name using the Deezer API and retrieves its track ID.
    :param track_name: The name of the track to search for.
    :return: The track ID or None if not found.
    """
    client = deezer.Client()
    results = client.search(track_name)  # Search for the track by name
    if results:
        track = results[0]  # Get the first result
        print(f"Found track: {track.title} by {track.artist.name}")
        return track.id
    else:
        print("Track not found.")
        return None

def main():
    track_name = "No Surprises"  # Replace with the name of the song
    track_id = get_track_id_by_name(track_name)
    
    if track_id:
        preview_url = get_song_preview(track_id)
        if preview_url:
            print(f"Preview URL: {preview_url}")
            audio_path = download_audio(preview_url)
            if audio_path:
                try:
                    features = extract_audio_features(audio_path)
                    sentiment = analyze_audio_sentiment(features)
                    print(f"Sentiment: {sentiment}")
                finally:
                    # Ensure the file is deleted even if an error occurs
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                        print(f"Deleted file: {audio_path}")
            else:
                print("Failed to download audio.")
        else:
            print("Could not fetch song preview.")
    else:
        print("Could not find track ID.")

if __name__ == "__main__":
    main()