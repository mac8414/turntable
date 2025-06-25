import os
import tempfile
import logging
import urllib.parse
import re
from cadence import EnhancedAudioProcessor
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

LASTFM_API_KEY="01af4ff32f2d0678564543a7e03fbd94"
LASTFM_API_SECRET="62768c8b386db357b36cc3d3afefa167"
API_URL = "http://ws.audioscrobbler.com/2.0/"

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

class LastFMClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        # Initialize LastFM client here if needed
    def get_similar_tracks(self, artist: str, track: str, limit: int = 100) -> List[Track]:
        params = {
            'method': 'track.getSimilar',
            'artist': artist,
            'track': track,
            'api_key': self.api_key,
            'format': 'json',
            'limit': limit  # Up to 100 max
        }
        
        response = requests.get(API_URL, params=params)
        data = response.json()
        
        if 'similartracks' not in data or 'track' not in data['similartracks']:
            print("No similar tracks found.")
            return []

        tracks = data['similartracks']['track']
        recommendations = []

        for idx, t in enumerate(tracks):
            title = t['name']
            artist_name = t['artist']['name']
            recommendations.append(Track(id=idx, title=title, artist_name=artist_name))

        return recommendations
    
    def get_top_tracks_by_similar_artist(self, artist, limit=40):
        # Step 1: Get similar artist
        similar_params = {
            'method': 'artist.getsimilar',
            'artist': artist,
            'api_key': LASTFM_API_KEY,
            'format': 'json',
            'limit': 1
        }
        response = requests.get(API_URL, params=similar_params)
        similar_data = response.json()
        similar_artist = similar_data.get('similarartists', {}).get('artist', [{}])[0].get('name')

        # Step 2: Get top tracks by similar artist
        if similar_artist:
            top_tracks_params = {
                'method': 'artist.gettoptracks',
                'artist': similar_artist,
                'api_key': LASTFM_API_KEY,
                'format': 'json',
                'limit': limit
            }
            response = requests.get(API_URL, params=top_tracks_params)
            top_tracks = response.json().get('toptracks', {}).get('track', [])
            return [(t['name'], similar_artist) for t in top_tracks]
        return []
    
    def get_artist_top_tracks(self, artist: str, limit: int = 10) -> List[Tuple[str, str]]:
        params = {
            'method': 'artist.gettoptracks',
            'artist': artist,
            'api_key': LASTFM_API_KEY,
            'format': 'json',
            'limit': limit
        }
        response = requests.get(API_URL, params=params)
        data = response.json()
        return [(t['name'], t['artist']['name']) for t in data.get('toptracks', {}).get('track', [])]
    
    def get_user_recommended_tracks(user, limit=10):
        params = {
            'method': 'user.getrecommendedtracks',
            'user': user,
            'api_key': LASTFM_API_KEY,
            'format': 'json',
            'limit': limit
        }
        response = requests.get(API_URL, params=params)
        data = response.json()
        return [(t['name'], t['artist']['name']) for t in data.get('recommendations', {}).get('track', [])]

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

    def get_track_id(self, track_name: str, artist_name: str) -> Optional[int]:
        """Gets the track ID using a track and artist name."""
        try:
            results = self.client.search(f"{track_name} {artist_name}")
            for track in results:
                if track.title.lower() == track_name.lower() and track.artist.name.lower() == artist_name.lower():
                    return track.id
            logger.info(f"Track '{track_name}' by '{artist_name}' not found.")
            return None
        except Exception as e:
            logger.error(f"Error getting track ID: {e}")
            return None
        
# Replace the AudioProcessor class and related methods in your crud.py with this updated version

class Track:
    def __init__(self, id: int, title: str, artist_name: str, preview_url: Optional[str] = None):
        self.id = id
        self.title = title
        self.artist_name = artist_name
        self.preview_url = preview_url
        self.features = None  # Will store AudioFeatures object
        self.feature_vector = None  # Will store numpy array for compatibility
        self.similarity_score = 0.0

    def __str__(self):
        return f"{self.title} by {self.artist_name}"

class MusicRecommender:
    def __init__(self):
        self.deezer_client = DeezerClient()
        self.audio_processor = EnhancedAudioProcessor()  # Use enhanced processor
        self.lastfm_client = LastFMClient(LASTFM_API_KEY, LASTFM_API_SECRET)
    
    def process_track(self, track: Track) -> Track:
        """Downloads and processes a single track to extract comprehensive features."""
        if not track.preview_url:
            track.preview_url = self.deezer_client.get_track_preview(track.id)
            
        if not track.preview_url:
            logger.warning(f"No preview URL available for track: {track}")
            return track
            
        temp_file = None
        try:
            logger.info(f"Processing: {track.title} by {track.artist_name}")
            temp_file = self.audio_processor.download_audio(track.preview_url)

            if temp_file:
                if not os.path.exists(temp_file) or os.path.getsize(temp_file) < 1024:
                    logger.warning(f"Downloaded file is missing or too small: {temp_file}")
                    return track
                logger.info(f"Downloaded to: {temp_file} ({os.path.getsize(temp_file)} bytes)")
                
                # Extract comprehensive features
                audio_features = self.audio_processor.extract_comprehensive_features(temp_file)
                
                if audio_features:
                    track.features = audio_features
                    track.feature_vector = audio_features.to_vector()
                    
                    logger.info(f"Extracted {len(track.feature_vector)} features for: {track.title}")
                    logger.info(f"  - Tempo: {audio_features.tempo:.1f} BPM")
                    logger.info(f"  - Key: {['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][audio_features.key_signature]} {'Major' if audio_features.mode else 'Minor'}")
                    logger.info(f"  - Spectral Centroid: {audio_features.spectral_centroid:.1f} Hz")
                    logger.info(f"  - Energy: {audio_features.rms_energy:.3f}")
                else:
                    logger.warning(f"Failed to extract features for: {track.title}")
            else:
                logger.warning(f"Failed to download preview for: {track.title}")
                
        except Exception as e:
            logger.error(f"Error processing track {track}: {e}")
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {temp_file}: {e}")
        
        return track
    
    def get_recommendations(self, track_name: str, artist_name: str, 
                          recommendations_count: int = FINAL_RECOMMENDATIONS_COUNT) -> List[Track]:
        """Gets and processes music recommendations based on enhanced audio feature similarity."""
        
        # Process the reference track
        track_id = self.deezer_client.search_track(track_name, artist_name)
        if not track_id:
            logger.error(f"Could not find reference track: {track_name} by {artist_name}")
            return []
        
        reference_track = Track(id=track_id, title=track_name, artist_name=artist_name)
        logger.info(f"Processing reference track: {reference_track.title} by {reference_track.artist_name}")
        reference_track = self.process_track(reference_track)
        
        if not reference_track.features:
            logger.error("Failed to extract features from reference track")
            return []
            
        # Log reference track characteristics
        ref_features = reference_track.features
        logger.info(f"Reference track analysis:")
        logger.info(f"  - Tempo: {ref_features.tempo:.1f} BPM")
        logger.info(f"  - Key: {['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][ref_features.key_signature]} {'Major' if ref_features.mode else 'Minor'}")
        logger.info(f"  - Energy: {ref_features.rms_energy:.3f}")
        logger.info(f"  - Brightness: {ref_features.spectral_centroid:.1f} Hz")
        
        # Fetch candidate tracks
        logger.info(f"Fetching recommendations for {track_name} by {artist_name}")

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_similar = executor.submit(
                self.lastfm_client.get_similar_tracks, artist_name, track_name, 50
            )

            future_top = executor.submit(
                self.lastfm_client.get_top_tracks_by_similar_artist, artist_name, 25
            )
            
            future_artist_top = executor.submit(
                self.lastfm_client.get_artist_top_tracks, artist_name, 25
            )

            similar_tracks = future_similar.result()
            top_tracks_tuples = future_top.result()
            artist_top_tracks = future_artist_top.result()

        # Convert tuples from get_top_tracks_by_similar_artist to Track objects
        top_tracks = [Track(id=1000 + i, title=title, artist_name=artist) for i, (title, artist) in enumerate(top_tracks_tuples)]
        artists_tracks = [Track(id=2000 + i, title=title, artist_name=artist) for i, (title, artist) in enumerate(artist_top_tracks)]

        # Concatenate both lists
        recommended_tracks = similar_tracks + top_tracks + artists_tracks 
        
        logger.info(f"Found {len(recommended_tracks)} candidate tracks")
        
        # Filter tracks
        filtered_tracks = self._filter_tracks(recommended_tracks, track_name, artist_name)
        logger.info(f"After filtering: {len(filtered_tracks)} tracks")
        
        # Update Deezer IDs
        valid_tracks = self._update_deezer_ids(filtered_tracks)
        logger.info(f"Found Deezer IDs for {len(valid_tracks)} tracks")
        
        # Process tracks in parallel
        if valid_tracks:
            with ThreadPoolExecutor(max_workers=min(8, len(valid_tracks))) as executor:
                processed_tracks = list(executor.map(self.process_track, valid_tracks))
        else:
            processed_tracks = []
        
        # Filter tracks with valid features
        tracks_with_features = [t for t in processed_tracks if t.features is not None]
        logger.info(f"Successfully processed {len(tracks_with_features)} tracks with features")
        
        if not tracks_with_features:
            logger.warning("No tracks with valid features found")
            return processed_tracks[:recommendations_count]
        
        # Calculate advanced similarities
        try:
            comparison_features = [t.features for t in tracks_with_features]
            similarities = self.audio_processor.calculate_advanced_similarity(
                reference_track.features, comparison_features
            )
            
            # Assign similarity scores
            for track, score in zip(tracks_with_features, similarities):
                track.similarity_score = score
                
            # Log some similarity details
            logger.info(f"Calculated similarities - Range: {min(similarities):.3f} to {max(similarities):.3f}")
            
        except Exception as e:
            logger.error(f"Error calculating similarities: {e}")
            for track in tracks_with_features:
                track.similarity_score = 0.5
        
        # Sort by similarity and return top recommendations
        tracks_with_features.sort(key=lambda x: x.similarity_score, reverse=True)
        
        final_recommendations = tracks_with_features[:recommendations_count]
        
        # Log final recommendations
        logger.info(f"Top {len(final_recommendations)} recommendations:")
        for i, rec in enumerate(final_recommendations, 1):
            logger.info(f"  {i}. {rec} (Score: {rec.similarity_score:.3f})")
        
        return final_recommendations
    
    def _filter_tracks(self, tracks: List[Track], reference_title: str, reference_artist: str) -> List[Track]:
        """Enhanced track filtering with better logic"""
        unwanted_keywords = [
            "extended", "remix", "live", "instrumental", "karaoke", 
            "acoustic", "cover", "demo", "unreleased", "alternate"
        ]
        
        filtered_tracks = []
        excluded_count = 0
        
        for track in tracks:
            # Skip exact matches
            if (track.title.lower().strip() == reference_title.lower().strip() and 
                track.artist_name.lower().strip() == reference_artist.lower().strip()):
                excluded_count += 1
                continue
                
            # Skip obvious variations of the reference track
            if (track.artist_name.lower().strip() == reference_artist.lower().strip() and
                any(keyword in track.title.lower() for keyword in ["remaster", "version", "edit", "deluxe"])):
                excluded_count += 1
                continue
                
            # Skip tracks with unwanted keywords
            if any(keyword in track.title.lower() for keyword in unwanted_keywords):
                excluded_count += 1
                continue
                
            filtered_tracks.append(track)
        
        logger.info(f"Filtered out {excluded_count} tracks")
        return filtered_tracks
    
    def _update_deezer_ids(self, tracks: List[Track]) -> List[Track]:
        """Update track IDs to real Deezer IDs and filter out unresolvable tracks"""
        valid_tracks = []
        
        for track in tracks:
            deezer_id = self.deezer_client.get_track_id(track.title, track.artist_name)
            if deezer_id:
                track.id = deezer_id
                valid_tracks.append(track)
            else:
                logger.debug(f"Could not resolve Deezer ID for: {track.title} by {track.artist_name}")
        
        return valid_tracks
    
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
        recommendations = recommender.get_recommendations(track_name, artist_name)  # Now works with default
        
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