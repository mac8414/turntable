import os
import tempfile
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

import deezer
import librosa
import numpy as np
import requests
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_PREVIEW_FILENAME = "preview.mp3"
TOP_RECOMMENDATIONS_COUNT = 50
SIMILAR_RECOMMENDATIONS_COUNT = 50
FINAL_RECOMMENDATIONS_COUNT = 5


@dataclass
class Track:
    id: int
    title: str
    artist_name: str
    preview_url: Optional[str] = None
    features: Optional[np.ndarray] = None
    similarity_score: float = 0.0

    def __str__(self):
        return f"{self.title} by {self.artist_name}"


class DeezerClient:
    def __init__(self):
        self.client = deezer.Client()
    
    def get_track_preview(self, track_id: int) -> Optional[str]:
        """Fetches the preview URL of a song from Deezer."""
        try:
            track = self.client.get_track(track_id)
            return track.preview
        except Exception as e:
            logger.error(f"Error fetching track preview: {e}")
            return None
    
    def search_track(self, track_name: str, artist_name: str) -> Optional[int]:
        """Searches for a track by name and artist, returns track ID if found."""
        try:
            results = self.client.search(f"{track_name} {artist_name}")
            for track in results:
                if track.artist.name.lower() == artist_name.lower():
                    return track.id
            logger.info(f"Track '{track_name}' by '{artist_name}' not found.")
            return None
        except Exception as e:
            logger.error(f"Error searching for track: {e}")
            return None
    
    def get_artist_id(self, track_name: str, artist_name: str) -> Optional[int]:
        """Gets the artist ID using a track and artist name."""
        try:
            results = self.client.search(f"{track_name} {artist_name}")
            for track in results:
                if track.artist.name.lower() == artist_name.lower():
                    return track.artist.id
            logger.info(f"Artist '{artist_name}' not found.")
            return None
        except Exception as e:
            logger.error(f"Error getting artist ID: {e}")
            return None
    
    def get_artist_top_tracks(self, track_name: str, artist_name: str, limit: int = 5) -> List[Track]:
        """Gets top tracks from the artist."""
        tracks = []
        artist_id = self.get_artist_id(track_name, artist_name)
        
        if not artist_id:
            return tracks
        
        try:
            artist = self.client.get_artist(artist_id)
            top_tracks = artist.get_top()
            
            for track in top_tracks[:limit]:
                tracks.append(Track(
                    id=track.id,
                    title=track.title,
                    artist_name=track.artist.name,
                    preview_url=track.preview
                ))
            
            return tracks
        except Exception as e:
            logger.error(f"Error getting artist top tracks: {e}")
            return tracks
    
    def get_similar_artist_tracks(self, track_name: str, artist_name: str, limit: int = 15) -> List[Track]:
        """Gets tracks from similar artists."""
        tracks = []
        artist_id = self.get_artist_id(track_name, artist_name)
        
        if not artist_id:
            return tracks
        
        try:
            artist = self.client.get_artist(artist_id)
            related_artists = artist.get_related()
            
            for related in related_artists:
                if len(tracks) >= limit:
                    break
                    
                try:
                    top_tracks = related.get_top()[:2]  # Get only 2 top tracks per similar artist
                    for track in top_tracks:
                        if len(tracks) >= limit:
                            break
                        tracks.append(Track(
                            id=track.id,
                            title=track.title,
                            artist_name=track.artist.name,
                            preview_url=track.preview
                        ))
                except Exception as e:
                    logger.warning(f"Error getting tracks for related artist {related.name}: {e}")
                    continue
            
            return tracks
        except Exception as e:
            logger.error(f"Error getting similar artist tracks: {e}")
            return tracks


class AudioProcessor:
    @staticmethod
    def download_audio(url: str, filename: Optional[str] = None) -> Optional[str]:
        """Downloads audio from a URL to a local file."""
        if not filename:
            # Create a temporary file with .mp3 extension that will be automatically deleted
            temp_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            filename = temp_file.name
            temp_file.close()
        
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.deezer.com",
            "Range": "bytes=0-"
        }
        
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            if response.status_code in [200, 206]:
                with open(filename, "wb") as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file.write(chunk)
                return filename
            else:
                logger.error(f"Error downloading audio: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Exception downloading audio: {e}")
            if os.path.exists(filename):
                os.remove(filename)
            return None
    
    @staticmethod
    def extract_audio_features(audio_path: str) -> Optional[np.ndarray]:
        """Extracts audio features from the given audio file."""
        try:
            y, sr = librosa.load(audio_path, sr=None)
            
            # Extract a variety of audio features
            features = []
            
            # MFCCs (Mel-frequency cepstral coefficients)
            mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            features.append(np.mean(mfccs.T, axis=0))
            
            # Spectral centroid (brightness)
            spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            features.append(np.mean(spectral_centroid.T, axis=0))
            
            # Spectral bandwidth (range of frequencies)
            spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
            features.append(np.mean(spectral_bandwidth.T, axis=0))
            
            # Spectral contrast
            spectral_contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
            features.append(np.mean(spectral_contrast.T, axis=0))
            
            # Tempo (BPM)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            features.append(np.array([tempo]))
            
            # Flatten and concatenate all features
            feature_vector = np.concatenate([f.flatten() for f in features])
            return feature_vector
            
        except Exception as e:
            logger.error(f"Error extracting audio features: {e}")
            return None
        
    @staticmethod
    def calculate_similarity(reference_features: np.ndarray, comparison_features: List[np.ndarray]) -> List[float]:
        """Calculates cosine similarity between reference features and a list of comparison features."""
        if not comparison_features:
            return []
            
        # Stack all comparison features into a 2D array
        comparison_matrix = np.vstack(comparison_features)
        
        # Scale features to have zero mean and unit variance
        scaler = StandardScaler()
        scaled_comparison = scaler.fit_transform(comparison_matrix)
        scaled_reference = scaler.transform(reference_features.reshape(1, -1))
        
        # Calculate cosine similarity
        similarities = cosine_similarity(scaled_reference, scaled_comparison)[0]
        return similarities.tolist()


class MusicRecommender:
    def __init__(self):
        self.deezer_client = DeezerClient()
        self.audio_processor = AudioProcessor()
    
    def process_track(self, track: Track) -> Track:
        """Downloads and processes a single track to extract features."""
        if not track.preview_url:
            track.preview_url = self.deezer_client.get_track_preview(track.id)
            
        if not track.preview_url:
            logger.warning(f"No preview URL available for track: {track}")
            return track
            
        temp_file = None
        try:
            temp_file = self.audio_processor.download_audio(track.preview_url)
            if temp_file:
                features = self.audio_processor.extract_audio_features(temp_file)
                if features is not None:
                    track.features = features
        except Exception as e:
            logger.error(f"Error processing track {track}: {e}")
        finally:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
                
        return track
    
    def get_recommendations(self, track_name: str, artist_name: str) -> List[Track]:
        """Gets and processes music recommendations."""
        # First, process the reference track to get its features
        track_id = self.deezer_client.search_track(track_name, artist_name)
        if not track_id:
            logger.error(f"Could not find reference track: {track_name} by {artist_name}")
            return []
            
        reference_track = Track(id=track_id, title=track_name, artist_name=artist_name)
        reference_track = self.process_track(reference_track)
        
        if reference_track.features is None:
            logger.error("Could not extract features from reference track")
            return []
        
        # Get recommendations from the same artist and similar artists
        artist_tracks = self.deezer_client.get_artist_top_tracks(
            track_name, artist_name, limit=TOP_RECOMMENDATIONS_COUNT)
        similar_tracks = self.deezer_client.get_similar_artist_tracks(
            track_name, artist_name, limit=SIMILAR_RECOMMENDATIONS_COUNT)
        
        all_tracks = artist_tracks + similar_tracks
        
        # Process all tracks in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            processed_tracks = list(executor.map(self.process_track, all_tracks))
        
        # Filter out tracks without features
        valid_tracks = [track for track in processed_tracks if track.features is not None]
        
        if not valid_tracks:
            logger.warning("No valid tracks with features found")
            return []
        
        # Calculate similarity scores
        feature_list = [track.features for track in valid_tracks]
        similarities = self.audio_processor.calculate_similarity(reference_track.features, feature_list)
        
        # Assign similarity scores
        for track, score in zip(valid_tracks, similarities):
            track.similarity_score = score
        
        # Filter out the input track from the recommendations
        valid_tracks = [
            track for track in valid_tracks
            if not (track.title.lower() == track_name.lower() and track.artist_name.lower() == artist_name.lower())
        ]
        
        # Sort by similarity score (descending)
        valid_tracks.sort(key=lambda x: x.similarity_score, reverse=True)
        
        # Return top recommendations
        return valid_tracks[:FINAL_RECOMMENDATIONS_COUNT]


def main():
    try:
        track_name = input("Enter the track name: ")
        artist_name = input("Enter the artist name: ")
        
        recommender = MusicRecommender()
        recommendations = recommender.get_recommendations(track_name, artist_name)
        
        print(f"\nTop {len(recommendations)} Recommendations for '{track_name}' by '{artist_name}':")
        for i, rec in enumerate(recommendations, start=1):
            print(f"{i}. {rec} (Similarity Score: {rec.similarity_score:.4f})")
            
    except Exception as e:
        logger.error(f"An error occurred in the main function: {e}")


if __name__ == "__main__":
    main()