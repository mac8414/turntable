import os
import tempfile
import logging
import urllib.parse
import re
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
TOP_RECOMMENDATIONS_COUNT = 25
SIMILAR_RECOMMENDATIONS_COUNT = 25
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

    def get_artist_radio(self, track_name: str, artist_name: str, limit: int = 50) -> List[Track]:
        """Gets tracks from the artist's radio."""
        tracks = []
        artist_id = self.get_artist_id(track_name, artist_name)
        
        if not artist_id:
            return tracks
        
        try:
            url = f"https://api.deezer.com/artist/{artist_id}/radio"
            response = requests.get(url)
            response.raise_for_status()  # Raise an error for HTTP issues
            data = response.json()
            
            for track_data in data.get("data", [])[:limit]:
                track_id = track_data.get("id")
                preview_url = track_data.get("preview")
                
                # If preview URL is missing, try to fetch it directly
                if not preview_url and track_id:
                    preview_url = self.get_track_preview(track_id)
                
                # Only add tracks that have a preview URL
                if preview_url:
                    tracks.append(Track(
                        id=track_id,
                        title=track_data.get("title"),
                        artist_name=track_data.get("artist", {}).get("name", "Unknown Artist"),
                        preview_url=preview_url
                    ))
                else:
                    logger.debug(f"Skipping track without preview: {track_data.get('title')}")
            
            return tracks
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.error(f"Error fetching artist radio: {e}")
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
        if not comparison_features or len(comparison_features) == 0:
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
                if features is not None and features.size > 0:  # Explicitly check size
                    track.features = features
                else:
                    logger.warning(f"Invalid features extracted for track: {track}")
        except Exception as e:
            logger.error(f"Error processing track {track}: {e}")
        finally:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
        
        return track
    
    def get_recommendations(self, track_name: str, artist_name: str) -> List[Track]:
        """Gets and processes music recommendations based on audio feature similarity."""
        # First, process the reference track to get its features
        track_id = self.deezer_client.search_track(track_name, artist_name)
        if not track_id:
            logger.error(f"Could not find reference track: {track_name} by {artist_name}")
            return []
        
        reference_track = Track(id=track_id, title=track_name, artist_name=artist_name)
        reference_track = self.process_track(reference_track)
        
        # Explicitly check if reference track features exist and are valid
        if reference_track.features is None or reference_track.features.size == 0:
            logger.error("Could not extract features from reference track")
            return []
        
        # Get recommendations from various sources with balanced distribution
        logger.info(f"Fetching recommendations for {track_name} by {artist_name}")
        
        # Calculate distribution for different recommendation sources
        artist_limit = TOP_RECOMMENDATIONS_COUNT 
        similar_limit = TOP_RECOMMENDATIONS_COUNT 
        radio_limit = TOP_RECOMMENDATIONS_COUNT 
        
        # Fetch recommendations in parallel for better performance
        with ThreadPoolExecutor(max_workers=3) as executor:
            artist_future = executor.submit(self.deezer_client.get_artist_top_tracks, 
                                        track_name, artist_name, limit=artist_limit)
            similar_future = executor.submit(self.deezer_client.get_similar_artist_tracks, 
                                            track_name, artist_name, limit=similar_limit)
            radio_future = executor.submit(self.deezer_client.get_artist_radio, 
                                        track_name, artist_name, limit=radio_limit)
            
            # Collect results
            artist_tracks = artist_future.result()
            similar_tracks = similar_future.result()
            radio_tracks = radio_future.result()
        
        # Log recommendation sources for debugging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Found {len(artist_tracks)} artist tracks, {len(similar_tracks)} similar tracks, {len(radio_tracks)} radio tracks")
            
            for i, track in enumerate(artist_tracks[:3], 1):
                logger.debug(f"Artist track {i}: {track.title} by {track.artist_name}")
            for i, track in enumerate(similar_tracks[:3], 1):
                logger.debug(f"Similar track {i}: {track.title} by {track.artist_name}")
            for i, track in enumerate(radio_tracks[:3], 1):
                logger.debug(f"Radio track {i}: {track.title} by {track.artist_name}")
        
        all_tracks = artist_tracks + similar_tracks + radio_tracks
        
        # Enhanced filtering logic
        unwanted_keywords = ["extended", "remix", "live", "instrumental", "karaoke", "acoustic", "cover"]
        filtered_tracks = []
        excluded_count = 0
        
        for track in all_tracks:
            # Skip exact matches to the reference track
            if (track.title.lower() == track_name.lower() and 
                track.artist_name.lower() == artist_name.lower()):
                excluded_count += 1
                continue
                
            # Skip variations of the reference track (like remasters)
            if (track.title.lower().startswith(track_name.lower()) and 
                track.artist_name.lower() == artist_name.lower() and
                any(keyword in track.title.lower() for keyword in ["remaster", "version", "edit"])):
                excluded_count += 1
                continue
                
            # Skip tracks with unwanted keywords
            if any(keyword in track.title.lower() for keyword in unwanted_keywords):
                excluded_count += 1
                continue
                
            # Track passes all filters
            filtered_tracks.append(track)
        
        logger.info(f"Filtered out {excluded_count} tracks, {len(filtered_tracks)} remaining")
        
        # Deduplicate tracks based on track ID
        track_dict = {}
        for track in filtered_tracks:
            track_dict[track.id] = track
        filtered_tracks = list(track_dict.values())
        
        logger.info(f"After deduplication: {len(filtered_tracks)} unique tracks")
        
        # Ensure we have enough tracks to process
        if len(filtered_tracks) < FINAL_RECOMMENDATIONS_COUNT:
            logger.warning(f"Not enough filtered tracks ({len(filtered_tracks)}), fetching additional recommendations")
            # If we don't have enough tracks, try getting more from similar artists with relaxed filters
            additional_tracks = self.deezer_client.get_similar_artist_tracks(
                track_name, artist_name, limit=SIMILAR_RECOMMENDATIONS_COUNT)
            
            # Add new tracks that aren't duplicates
            for track in additional_tracks:
                if track.id not in track_dict:
                    filtered_tracks.append(track)
                    track_dict[track.id] = track
        
        # Process tracks in parallel with a process pool for CPU-intensive feature extraction
        processed_tracks = []
        if filtered_tracks:
            with ThreadPoolExecutor(max_workers=min(8, len(filtered_tracks))) as executor:
                processed_tracks = list(executor.map(self.process_track, filtered_tracks))
        
        # Filter out tracks without features - explicit check for None and empty arrays
        valid_tracks = []
        for track in processed_tracks:
            if track.features is not None and track.features.size > 0:
                valid_tracks.append(track)
        # Filter out tracks without features 
        if not valid_tracks:
            logger.warning("No valid tracks with features found")
            return []
        
        # Calculate similarity scores
        feature_list = [track.features for track in valid_tracks]
        similarities = self.audio_processor.calculate_similarity(reference_track.features, feature_list)
        
        # Assign similarity scores and add source info for debugging
        for track, score in zip(valid_tracks, similarities):
            track.similarity_score = float(score)  # Ensure score is a Python float, not NumPy type
            
            # Determine the source for logging purposes
            source = "unknown"
            if any(track.id == t.id for t in artist_tracks):
                source = "artist"
            elif track in similar_tracks:
                source = "similar"
            elif track in radio_tracks:
                source = "radio"
            
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Track '{track.title}' by {track.artist_name} from {source} source has similarity score: {score:.4f}")
        
        # Sort by similarity score (descending)
        valid_tracks.sort(key=lambda x: x.similarity_score, reverse=True)
        
        # Ensure diversity in final recommendations (at least one from each source if possible)
        final_recommendations = []
        source_counts = {"artist": 0, "similar": 0, "radio": 0}
        
        # First, try to include at least one track from each source
        for source in ["artist", "similar", "radio"]:
            source_tracks = locals()[f"{source}_tracks"]
            for track in valid_tracks:
                # Use explicit check for membership without relying on __eq__
                if any(t.id == track.id for t in source_tracks) and not any(r.id == track.id for r in final_recommendations):
                    final_recommendations.append(track)
                    source_counts[source] += 1
                    break
        
        # Then fill the remaining slots with the highest similarity scores
        remaining_slots = FINAL_RECOMMENDATIONS_COUNT - len(final_recommendations)
        if remaining_slots > 0:
            # Add remaining tracks by similarity score, skipping those already included
            for track in valid_tracks:
                if not any(r.id == track.id for r in final_recommendations):
                    final_recommendations.append(track)
                    remaining_slots -= 1
                    if remaining_slots == 0:
                        break
        
        # Log final recommendation sources
        if logger.isEnabledFor(logging.INFO):
            logger.info(f"Final recommendations include {source_counts['artist']} artist tracks, "
                    f"{source_counts['similar']} similar artist tracks, and {source_counts['radio']} radio tracks")
        
        return final_recommendations[:FINAL_RECOMMENDATIONS_COUNT]

def clean_track_name(track_name: str) -> str:
    """
    Cleans the track name by removing unwanted text like "(explicit version)"
    and normalizing whitespace.
    """
    # Remove text in parentheses (e.g., "(explicit version)", "(Extended Remix)")
    cleaned_name = re.sub(r"\(.*?\)", "", track_name)
    # Normalize whitespace
    cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip()
    return cleaned_name

def clean_artist_name(artist_name: str) -> str:
    """
    Cleans the artist name by normalizing whitespace.
    """
    # Normalize whitespace
    return re.sub(r"\s+", " ", artist_name).strip()

def get_spotify_search_link(track_name: str, artist_name: str) -> str:
    """
    Generates a Spotify search link for the given track and artist.
    """
    cleaned_track_name = clean_track_name(track_name)
    cleaned_artist_name = clean_artist_name(artist_name)
    query = f"{cleaned_track_name} {cleaned_artist_name}"
    encoded_query = urllib.parse.quote(query)
    return f"https://open.spotify.com/search/{encoded_query}"

def get_apple_music_search_link(track_name: str, artist_name: str) -> str:
    """
    Generates an Apple Music search link for the given track and artist.
    """
    cleaned_track_name = clean_track_name(track_name)
    cleaned_artist_name = clean_artist_name(artist_name)
    query = f"{cleaned_track_name} {cleaned_artist_name}"
    encoded_query = urllib.parse.quote(query)
    return f"https://music.apple.com/us/search?term={encoded_query}"

def main():
    try:
        track_name = input("Enter the track name: ")
        artist_name = input("Enter the artist name: ")
        
        recommender = MusicRecommender()
        recommendations = recommender.get_recommendations(track_name, artist_name)
        
        print(f"\nTop {len(recommendations)} Recommendations for '{track_name}' by '{artist_name}':")
        for i, rec in enumerate(recommendations, start=1):
            print(f"{i}. {rec} (Similarity Score: {rec.similarity_score * 100:.2f}%)")
            print(get_spotify_search_link(rec.title, rec.artist_name))
            print(get_apple_music_search_link(rec.title, rec.artist_name))
            print()
            
    except Exception as e:
        logger.error(f"An error occurred in the main function: {e}")

if __name__ == "__main__":
    main()