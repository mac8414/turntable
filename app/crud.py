import os
import logging
import urllib.parse
import re
import time
from cadence import EnhancedAudioProcessor
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Optional, Tuple, Callable

import deezer
import numpy as np
import requests
from dotenv import load_dotenv

# Load variables from .env into the environment
load_dotenv()

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

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_SECRET = os.getenv("LASTFM_API_SECRET")
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

class ProgressCallback:
    """Callback interface for progress updates"""
    def __init__(self, callback_func: Optional[Callable[[str, int], None]] = None):
        self.callback_func = callback_func
    
    def update(self, message: str, progress: int = 0):
        """Update progress with message and percentage (0-100)"""
        if self.callback_func:
            self.callback_func(message, progress)
        logger.info(f"Progress ({progress}%): {message}")

class LastFMClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        
    def get_similar_tracks(self, artist: str, track: str, limit: int = 100) -> List[Track]:
        params = {
            'method': 'track.getSimilar',
            'artist': artist,
            'track': track,
            'api_key': self.api_key,
            'format': 'json',
            'limit': limit
        }
        
        try:
            response = requests.get(API_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"LastFM API error: {e}")
            return []
        
        if 'similartracks' not in data or 'track' not in data['similartracks']:
            logger.warning("No similar tracks found in LastFM response")
            return []

        tracks = data['similartracks']['track']
        recommendations = []

        for idx, t in enumerate(tracks):
            title = t.get('name', 'Unknown')
            artist_name = t.get('artist', {}).get('name', 'Unknown')
            recommendations.append(Track(id=idx, title=title, artist_name=artist_name))

        return recommendations
    
    def get_top_tracks_by_similar_artist(self, artist, limit=40):
        try:
            # Step 1: Get similar artist
            similar_params = {
                'method': 'artist.getsimilar',
                'artist': artist,
                'api_key': self.api_key,
                'format': 'json',
                'limit': 1
            }
            response = requests.get(API_URL, params=similar_params, timeout=15)
            response.raise_for_status()
            similar_data = response.json()
            
            artist_list = similar_data.get('similarartists', {}).get('artist', [])
            if not artist_list:
                logger.warning(f"No similar artists found for '{artist}'")
                return []
            similar_artist = artist_list[0].get('name')

            # Step 2: Get top tracks by similar artist
            if similar_artist:
                top_tracks_params = {
                    'method': 'artist.gettoptracks',
                    'artist': similar_artist,
                    'api_key': self.api_key,
                    'format': 'json',
                    'limit': limit
                }
                response = requests.get(API_URL, params=top_tracks_params, timeout=15)
                response.raise_for_status()
                top_tracks_data = response.json()
                top_tracks = top_tracks_data.get('toptracks', {}).get('track', [])
                return [(t.get('name', 'Unknown'), similar_artist) for t in top_tracks]
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting top tracks by similar artist: {e}")
        return []
    
    def get_artist_top_tracks(self, artist: str, limit: int = 10) -> List[Tuple[str, str]]:
        try:
            params = {
                'method': 'artist.gettoptracks',
                'artist': artist,
                'api_key': self.api_key,
                'format': 'json',
                'limit': limit
            }
            response = requests.get(API_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            tracks = data.get('toptracks', {}).get('track', [])
            return [(t.get('name', 'Unknown'), t.get('artist', {}).get('name', artist)) for t in tracks]
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting artist top tracks: {e}")
        return []

class DeezerClient:
    def __init__(self):
        self.client = deezer.Client()
        self._search_cache = {}
    
    def get_track_preview(self, track_id: int) -> Optional[str]:
        try:
            track = self.client.get_track(track_id)
            return track.preview
        except Exception as e:
            logger.error(f"Error fetching track preview: {e}")
            return None
    
    def search_track(self, track_name: str, artist_name: str) -> Optional[int]:
        cache_key = f"{track_name.lower()}|{artist_name.lower()}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]
            
        try:
            results = self.client.search(f"{track_name} {artist_name}")
            for track in results:
                if track.artist.name.lower() == artist_name.lower():
                    self._search_cache[cache_key] = track.id
                    return track.id
            logger.debug(f"Track '{track_name}' by '{artist_name}' not found.")
            self._search_cache[cache_key] = None
            return None
        except Exception as e:
            logger.error(f"Error searching for track: {e}")
            return None
    
    def get_track_id(self, track_name: str, artist_name: str) -> Optional[int]:
        cache_key = f"id_{track_name.lower()}|{artist_name.lower()}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]
            
        try:
            results = self.client.search(f"{track_name} {artist_name}")
            for track in results:
                if (track.title.lower() == track_name.lower() and 
                    track.artist.name.lower() == artist_name.lower()):
                    self._search_cache[cache_key] = track.id
                    return track.id
            logger.debug(f"Exact track '{track_name}' by '{artist_name}' not found.")
            self._search_cache[cache_key] = None
            return None
        except Exception as e:
            logger.error(f"Error getting track ID: {e}")
            return None

class MusicRecommender:
    def __init__(self):
        self.deezer_client = DeezerClient()
        self.audio_processor = EnhancedAudioProcessor()
        self.lastfm_client = LastFMClient(LASTFM_API_KEY, LASTFM_API_SECRET)
    
    def process_track(self, track: Track, progress_callback: Optional[ProgressCallback] = None) -> Track:
        """Downloads and processes a single track to extract comprehensive features."""
        if progress_callback:
            progress_callback.update(f"Processing: {track.title}")
            
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
                          recommendations_count: int = FINAL_RECOMMENDATIONS_COUNT,
                          progress_callback: Optional[ProgressCallback] = None) -> List[Track]:
        """Gets and processes music recommendations with progress updates."""
        
        try:
            if progress_callback:
                progress_callback.update("Starting recommendation process...", 5)
            
            # Process the reference track
            if progress_callback:
                progress_callback.update("Finding reference track...", 10)
                
            track_id = self.deezer_client.search_track(track_name, artist_name)
            if not track_id:
                error_msg = f"Could not find reference track: {track_name} by {artist_name}"
                logger.error(error_msg)
                if progress_callback:
                    progress_callback.update(f"Error: {error_msg}", 0)
                return []
            
            reference_track = Track(id=track_id, title=track_name, artist_name=artist_name)
            logger.info(f"Processing reference track: {reference_track.title} by {reference_track.artist_name}")
            
            if progress_callback:
                progress_callback.update("Analyzing reference track...", 20)
                
            reference_track = self.process_track(reference_track, progress_callback)
            
            if not reference_track.features:
                error_msg = "Failed to extract features from reference track"
                logger.error(error_msg)
                if progress_callback:
                    progress_callback.update(f"Error: {error_msg}", 0)
                return []
            
            # Fetch candidate tracks
            if progress_callback:
                progress_callback.update("Fetching similar tracks...", 30)
                
            logger.info(f"Fetching recommendations for {track_name} by {artist_name}")

            with ThreadPoolExecutor(max_workers=3) as executor:
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

            # Convert tuples to Track objects
            top_tracks = [Track(id=1000 + i, title=title, artist_name=artist) 
                         for i, (title, artist) in enumerate(top_tracks_tuples)]
            artists_tracks = [Track(id=2000 + i, title=title, artist_name=artist) 
                            for i, (title, artist) in enumerate(artist_top_tracks)]

            # Concatenate all tracks
            recommended_tracks = similar_tracks + top_tracks + artists_tracks 
            logger.info(f"Found {len(recommended_tracks)} candidate tracks")
            
            if progress_callback:
                progress_callback.update("Filtering candidate tracks...", 40)
            
            # Filter tracks
            filtered_tracks = self._filter_tracks(recommended_tracks, track_name, artist_name)
            logger.info(f"After filtering: {len(filtered_tracks)} tracks")
            
            if not filtered_tracks:
                error_msg = "No suitable candidate tracks found after filtering"
                logger.warning(error_msg)
                if progress_callback:
                    progress_callback.update(error_msg, 0)
                return []
            
            if progress_callback:
                progress_callback.update("Finding tracks on Deezer...", 50)
            
            # Update Deezer IDs
            valid_tracks = self._update_deezer_ids(filtered_tracks)
            logger.info(f"Found Deezer IDs for {len(valid_tracks)} tracks")
            
            if not valid_tracks:
                error_msg = "No tracks found on Deezer"
                logger.warning(error_msg)
                if progress_callback:
                    progress_callback.update(error_msg, 0)
                return []
            
            if progress_callback:
                progress_callback.update("Analyzing audio features...", 60)
            
            # Process tracks in parallel with progress updates
            processed_tracks = []
            total_tracks = len(valid_tracks)
            
            def process_with_progress(track_idx_pair):
                track, idx = track_idx_pair
                if progress_callback:
                    base_progress = 60
                    track_progress = int(30 * (idx + 1) / total_tracks)
                    progress_callback.update(f"Processing track {idx + 1}/{total_tracks}: {track.title}", 
                                           base_progress + track_progress)
                return self.process_track(track)
            
            track_idx_pairs = [(track, idx) for idx, track in enumerate(valid_tracks)]
            
            with ThreadPoolExecutor(max_workers=min(4, len(valid_tracks))) as executor:
                processed_tracks = list(executor.map(process_with_progress, track_idx_pairs))
            
            # Filter tracks with valid features
            tracks_with_features = [t for t in processed_tracks if t.features is not None]
            logger.info(f"Successfully processed {len(tracks_with_features)} tracks with features")
            
            if not tracks_with_features:
                logger.warning("No tracks with valid features found")
                if progress_callback:
                    progress_callback.update("Warning: No audio features extracted, returning basic results", 95)
                return processed_tracks[:recommendations_count]
            
            if progress_callback:
                progress_callback.update("Calculating similarities...", 95)
            
            # Calculate advanced similarities
            try:
                comparison_features = [t.features for t in tracks_with_features]
                similarities = self.audio_processor.calculate_advanced_similarity(
                    reference_track.features, comparison_features
                )
                
                # Assign similarity scores
                for track, score in zip(tracks_with_features, similarities):
                    track.similarity_score = score
                    
                logger.info(f"Calculated similarities - Range: {min(similarities):.3f} to {max(similarities):.3f}")
                
            except Exception as e:
                logger.error(f"Error calculating similarities: {e}")
                for track in tracks_with_features:
                    track.similarity_score = 0.5
            
            # Sort by similarity and return top recommendations
            tracks_with_features.sort(key=lambda x: x.similarity_score, reverse=True)
            
            final_recommendations = tracks_with_features[:recommendations_count]
            
            if progress_callback:
                progress_callback.update("Recommendations complete!", 100)
            
            # Log final recommendations
            logger.info(f"Top {len(final_recommendations)} recommendations for '{track_name}' by '{artist_name}':")
            for i, rec in enumerate(final_recommendations, 1):
                logger.info(f"  {i}. {rec} (Score: {rec.similarity_score:.3f})")
            
            return final_recommendations
            
        except Exception as e:
            error_msg = f"Error in recommendation process: {str(e)}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback.update(error_msg, 0)
            return []
    
    def _filter_tracks(self, tracks: List[Track], reference_title: str, reference_artist: str) -> List[Track]:
        unwanted_keywords = [
            "extended", "remix", "live", "instrumental", "karaoke", 
            "acoustic", "cover", "demo", "unreleased", "alternate",
            "coconut"  # Your specific filter
        ]
        
        filtered_tracks = []
        excluded_count = 0
        seen = set()
        
        for track in tracks:
            key = (track.title.lower().strip(), track.artist_name.lower().strip())
            
            # Skip exact matches to reference
            if key == (reference_title.lower().strip(), reference_artist.lower().strip()):
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
                
            # Skip duplicates
            if key in seen:
                excluded_count += 1
                continue

            seen.add(key)
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

# Utility functions remain the same
def clean_track_name(track_name: str) -> str:
    """Cleans the track name by removing unwanted text and normalizing whitespace."""
    cleaned_name = re.sub(r"\(.*?\)", "", track_name)
    cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip()
    return cleaned_name

def clean_artist_name(artist_name: str) -> str:
    """Cleans the artist name by normalizing whitespace."""
    return re.sub(r"\s+", " ", artist_name).strip()

def get_spotify_search_link(track_name: str, artist_name: str) -> str:
    """Generates a Spotify search link for the given track and artist."""
    cleaned_track_name = clean_track_name(track_name)
    cleaned_artist_name = clean_artist_name(artist_name)
    query = f"{cleaned_track_name} {cleaned_artist_name}"
    encoded_query = urllib.parse.quote(query)
    return f"https://open.spotify.com/search/{encoded_query}"

def get_apple_music_search_link(track_name: str, artist_name: str) -> str:
    """Generates an Apple Music search link for the given track and artist."""
    cleaned_track_name = clean_track_name(track_name)
    cleaned_artist_name = clean_artist_name(artist_name)
    query = f"{cleaned_track_name} {cleaned_artist_name}"
    encoded_query = urllib.parse.quote(query)
    return f"https://music.apple.com/us/search?term={encoded_query}"

def main():
    def progress_handler(message: str, progress: int):
        """Simple progress handler for console output"""
        print(f"[{progress:3d}%] {message}")
    
    try:
        track_name = input("Enter the track name: ")
        artist_name = input("Enter the artist name: ")
        
        recommender = MusicRecommender()
        progress_callback = ProgressCallback(progress_handler)
        
        recommendations = recommender.get_recommendations(
            track_name, artist_name, 
            progress_callback=progress_callback
        )
        
        if recommendations:
            print(f"\nTop {len(recommendations)} Recommendations for '{track_name}' by '{artist_name}':")
            for i, rec in enumerate(recommendations, start=1):
                print(f"{i}. {rec} (Similarity Score: {rec.similarity_score * 100:.2f}%)")
                print(f"   Spotify: {get_spotify_search_link(rec.title, rec.artist_name)}")
                print(f"   Apple Music: {get_apple_music_search_link(rec.title, rec.artist_name)}")
                print()
        else:
            print("No recommendations found. Please try a different track or artist.")
            
    except Exception as e:
        logger.error(f"An error occurred in the main function: {e}")

if __name__ == "__main__":
    main()