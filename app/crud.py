import os
import logging
import re
import threading
import time
import unicodedata
import urllib.parse
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import deezer
import requests
from dotenv import load_dotenv

from cadence import AudioFeatures, EnhancedAudioProcessor

# Load variables from .env into the environment
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
FINAL_RECOMMENDATIONS_COUNT = 5
MAX_RECOMMENDATIONS_COUNT = 10
SIMILAR_TRACKS_LIMIT = 60
SIMILAR_ARTISTS_LIMIT = 8
TRACKS_PER_SIMILAR_ARTIST = 5
SEED_ARTIST_TRACKS_LIMIT = 10
MAX_POOL_TRACKS_PER_ARTIST = 3   # keep the analyzed pool from being dominated by one artist
MIN_ANALYSIS_POOL = 30           # how many candidates to download and analyze

# Final score = blend of how a track sounds and how listeners relate it (Last.fm)
AUDIO_WEIGHT = 0.65
CONTEXT_WEIGHT = 0.35

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_SECRET = os.getenv("LASTFM_API_SECRET")
# Use HTTPS for Last.fm API
API_URL = "https://ws.audioscrobbler.com/2.0/"

# Annotations in (), [] or after " - " that mark a track as an alternate recording
ALTERNATE_VERSION_WORDS = re.compile(
    r"\b(remix|live|instrumental|karaoke|acoustic|cover|demo|unreleased|alternate|extended|"
    r"sped up|slowed|nightcore|reverb|8d)\b"
)
BLOCKED_TITLE_WORDS = ["coconut"]

# Last.fm tags that count as each genre on the Genre knob
GENRE_TAGS = {
    'rock': ['rock', 'grunge', 'punk', 'alternative', 'britpop', 'shoegaze'],
    'pop': ['pop'],
    'hip-hop': ['hip-hop', 'hip hop', 'hiphop', 'rap', 'trap', 'grime', 'drill'],
    'electronic': ['electronic', 'electronica', 'edm', 'house', 'techno', 'trance', 'dubstep',
                   'drum and bass', 'dnb', 'ambient', 'idm', 'synthpop', 'synthwave', 'dance'],
    'jazz': ['jazz', 'bebop', 'swing', 'fusion'],
    'classical': ['classical', 'orchestral', 'baroque', 'opera', 'symphony', 'composer', 'piano'],
    'r&b': ['r&b', 'rnb', 'rhythm and blues', 'soul', 'neo-soul', 'funk', 'motown'],
    'country': ['country', 'americana', 'bluegrass', 'honky tonk'],
    'metal': ['metal', 'metalcore', 'deathcore', 'djent'],
}


@dataclass
class Track:
    id: int
    title: str
    artist_name: str
    preview_url: Optional[str] = None
    album_cover: Optional[str] = None
    release_year: Optional[int] = None
    features: Optional[AudioFeatures] = None
    context_score: float = 0.0     # how strongly Last.fm listeners relate this track to the seed
    audio_score: Optional[float] = None
    similarity_score: float = 0.0  # final blended score, 0-1

    def __str__(self):
        return f"{self.title} by {self.artist_name}"


@dataclass
class RecommendationResult:
    tracks: List[Track] = field(default_factory=list)
    notices: List[str] = field(default_factory=list)


class ProgressCallback:
    """Callback interface for progress updates"""
    def __init__(self, callback_func: Optional[Callable[[str, int], None]] = None):
        self.callback_func = callback_func

    def update(self, message: str, progress: int = 0):
        """Update progress with message and percentage (0-100)"""
        if self.callback_func:
            self.callback_func(message, progress)
        logger.info(f"Progress ({progress}%): {message}")


class LRUCache:
    """Small thread-safe LRU cache with optional expiry that can also cache None results."""
    _MISSING = object()

    def __init__(self, max_size: int = 1000, ttl: Optional[float] = None):
        self.max_size = max_size
        self.ttl = ttl
        self._data = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._data:
                return self._MISSING
            value, expires_at = self._data[key]
            if expires_at is not None and time.monotonic() > expires_at:
                del self._data[key]
                return self._MISSING
            self._data.move_to_end(key)
            return value

    def set(self, key, value):
        with self._lock:
            expires_at = time.monotonic() + self.ttl if self.ttl else None
            self._data[key] = (value, expires_at)
            self._data.move_to_end(key)
            if len(self._data) > self.max_size:
                self._data.popitem(last=False)

    def get_or_compute(self, key, compute: Callable):
        value = self.get(key)
        if value is self._MISSING:
            value = compute()
            self.set(key, value)
        return value


class RateLimiter:
    """Allows at most max_calls per period seconds across all threads."""
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self._calls = deque()
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] > self.period:
                self._calls.popleft()
            if len(self._calls) >= self.max_calls:
                time.sleep(self.period - (now - self._calls[0]))
                now = time.monotonic()
                while self._calls and now - self._calls[0] > self.period:
                    self._calls.popleft()
            self._calls.append(now)


# --- Name normalization ---

def _strip_accents(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))


def _version_annotations(title: str) -> str:
    """Text inside brackets or after ' - ', e.g. 'Live at Wembley' from 'Song - Live at Wembley'."""
    parts = re.findall(r"[\(\[]([^\)\]]*)[\)\]]", title)
    if ' - ' in title:
        parts.append(title.split(' - ', 1)[1])
    return ' '.join(parts).lower()


def is_alternate_version(title: str) -> bool:
    return bool(ALTERNATE_VERSION_WORDS.search(_version_annotations(title)))


def normalize_title(title: str) -> str:
    """'Black (2009 Remaster) - Live' -> 'black'"""
    title = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", title)
    title = title.split(' - ', 1)[0]
    title = re.sub(r"\b(feat|ft|featuring)\.?\s.*$", "", title, flags=re.IGNORECASE)
    title = _strip_accents(title).lower().replace('&', 'and')
    title = re.sub(r"[^\w\s]", "", title)
    return re.sub(r"\s+", " ", title).strip()


def display_title(title: str) -> str:
    """'The Chain - 2004 Remaster' -> 'The Chain'. Keeps other annotations like '(feat. X)'."""
    title = re.sub(r"\s*[\(\[][^\)\]]*remaster[^\)\]]*[\)\]]", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+-\s+[^-]*remaster.*$", "", title, flags=re.IGNORECASE)
    return title.strip()


def normalize_artist(artist: str) -> str:
    """'The Beatles' -> 'beatles', 'Beyoncé feat. JAY-Z' -> 'beyonce'"""
    artist = re.sub(r"\s+(feat|ft|featuring)\.?\s.*$", "", artist, flags=re.IGNORECASE)
    artist = _strip_accents(artist).lower().replace('&', 'and')
    artist = re.sub(r"[^\w\s]", "", artist)
    artist = re.sub(r"^the\s+", "", artist)
    return re.sub(r"\s+", " ", artist).strip()


def artists_match(a: str, b: str) -> bool:
    """Exact match after normalizing, or a collaboration credit ('Bob Marley' / 'Bob Marley & The Wailers')."""
    a, b = normalize_artist(a), normalize_artist(b)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    return any(longer.startswith(f"{shorter} {joiner} ") for joiner in ('and', 'with', 'x', 'vs'))


def parse_timeframe(timeframe: Optional[str]) -> Optional[Tuple[int, int]]:
    """'80s' -> (1980, 1989), '2010s' -> (2010, 2019). None for 'Any' or unknown values."""
    match = re.fullmatch(r"(\d{2}|\d{4})s", (timeframe or '').strip().lower())
    if not match:
        return None
    start = int(match.group(1))
    if start < 100:
        start += 1900 if start >= 30 else 2000
    return start, start + 9


def genre_matches(tags: List[str], genre: str) -> bool:
    keywords = GENRE_TAGS.get(genre.lower(), [genre.lower()])
    return any(keyword in tag for tag in tags for keyword in keywords)


class LastFMClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self._cache = LRUCache(max_size=2000, ttl=24 * 3600)

    def _get(self, method: str, **params) -> Optional[dict]:
        if not self.api_key:
            logger.error(f"LastFM API key is not configured ({method})")
            return None
        params.update({'method': method, 'api_key': self.api_key, 'format': 'json', 'autocorrect': 1})
        try:
            response = requests.get(API_URL, params=params, timeout=10)
            if not response.ok:
                logger.error(f"LastFM HTTP error ({response.status_code}) for {method}: {response.text[:200]}")
                return None
            data = response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.error(f"LastFM request error for {method}: {e}")
            return None
        if 'error' in data:
            logger.warning(f"LastFM error for {method}: {data.get('message')}")
            return None
        return data

    def get_similar_tracks(self, artist: str, track: str, limit: int = SIMILAR_TRACKS_LIMIT) -> List[Track]:
        data = self._get('track.getSimilar', artist=artist, track=track, limit=limit) or {}
        tracks = data.get('similartracks', {}).get('track', [])
        return [
            Track(id=0, title=t.get('name', ''), artist_name=t.get('artist', {}).get('name', ''),
                  context_score=float(t.get('match') or 0))
            for t in tracks
        ]

    def get_similar_artists(self, artist: str, limit: int = SIMILAR_ARTISTS_LIMIT) -> List[Tuple[str, float]]:
        def fetch():
            data = self._get('artist.getSimilar', artist=artist, limit=limit) or {}
            artists = data.get('similarartists', {}).get('artist', [])
            return [(a.get('name', ''), float(a.get('match') or 0)) for a in artists]
        return self._cache.get_or_compute(('similar_artists', artist.lower(), limit), fetch)

    def get_artist_top_tracks(self, artist: str, limit: int = 10) -> List[Tuple[str, str]]:
        def fetch():
            data = self._get('artist.getTopTracks', artist=artist, limit=limit) or {}
            tracks = data.get('toptracks', {}).get('track', [])
            return [(t.get('name', ''), t.get('artist', {}).get('name', artist)) for t in tracks][:limit]
        return self._cache.get_or_compute(('top_tracks', artist.lower(), limit), fetch)

    def get_artist_tags(self, artist: str, limit: int = 8) -> List[str]:
        def fetch():
            data = self._get('artist.getTopTags', artist=artist) or {}
            tags = data.get('toptags', {}).get('tag', [])
            return [t.get('name', '').lower() for t in tags[:limit]]
        return self._cache.get_or_compute(('tags', artist.lower()), fetch)


class DeezerClient:
    def __init__(self):
        self.client = deezer.Client()
        # Preview URLs from Deezer expire, so don't hold on to results for long
        self._cache = LRUCache(max_size=3000, ttl=10 * 60)
        # Deezer allows 50 requests per 5 seconds per IP
        self._rate_limiter = RateLimiter(max_calls=45, period=5.0)

    def _call(self, fn: Callable, *args, **kwargs):
        for attempt in range(2):
            self._rate_limiter.wait()
            try:
                return fn(*args, **kwargs)
            except deezer.exceptions.DeezerErrorResponse as e:
                # Error code 4 is "quota exceeded"; wait it out once
                if attempt == 0 and (e.json_data or {}).get('error', {}).get('code') == 4:
                    time.sleep(1.5)
                    continue
                raise

    def search(self, query: str, limit: int = 20) -> list:
        """Raw Deezer track search. Slicing avoids paging through every result."""
        def fetch():
            return list(self._call(lambda: self.client.search(query)[:limit]))
        return self._cache.get_or_compute(('search', query.lower(), limit), fetch)

    def get_track(self, track_id: int):
        return self._cache.get_or_compute(('track', track_id), lambda: self._call(self.client.get_track, track_id))

    @staticmethod
    def _to_track(result, context_score: float = 0.0) -> Track:
        return Track(
            id=result.id,
            title=result.title,
            artist_name=result.artist.name,
            preview_url=result.preview or None,
            album_cover=result.album.cover_medium or result.album.cover,
            context_score=context_score,
        )

    def find_track(self, title: str, artist: str) -> Optional[Track]:
        """Find the original recording of a track on Deezer, preferring non-live/remix versions."""
        def fetch():
            try:
                results = self.search(f"{artist} {normalize_title(title) or title}", limit=15)
            except Exception as e:
                logger.error(f"Error searching Deezer for {title} by {artist}: {e}")
                return None
            wanted = normalize_title(title)
            matches = [
                r for r in results
                if artists_match(r.artist.name, artist) and normalize_title(r.title) == wanted
            ]
            if not matches:
                return None
            # Prefer studio versions, then ones with a preview, then the most popular
            matches.sort(key=lambda r: (is_alternate_version(r.title), not r.preview, -(r.rank or 0)))
            return self._to_track(matches[0])
        return self._cache.get_or_compute(('find', normalize_title(title), normalize_artist(artist)), fetch)

    def release_year(self, track_id: int) -> Optional[int]:
        try:
            release_date = self.get_track(track_id).release_date
            return release_date.year if release_date else None
        except Exception as e:
            logger.debug(f"Could not get release date for {track_id}: {e}")
            return None


class MusicRecommender:
    def __init__(self):
        self.deezer_client = DeezerClient()
        self.audio_processor = EnhancedAudioProcessor()
        self.lastfm_client = LastFMClient(LASTFM_API_KEY, LASTFM_API_SECRET)
        self._features_cache = LRUCache(max_size=2000)

    def analyze_track(self, track: Track) -> Track:
        """Download the track's preview and extract audio features (cached per Deezer ID)."""
        def compute():
            if not track.preview_url:
                return None
            temp_file = self.audio_processor.download_audio(track.preview_url)
            if not temp_file:
                return None
            try:
                return self.audio_processor.extract_comprehensive_features(temp_file)
            finally:
                if os.path.exists(temp_file):
                    os.remove(temp_file)

        try:
            features = self._features_cache.get(track.id)
            if features is LRUCache._MISSING:
                features = compute()
                # Only cache successes so a flaky download can be retried next time
                if features is not None:
                    self._features_cache.set(track.id, features)
            track.features = features
        except Exception as e:
            logger.error(f"Error analyzing track {track}: {e}")
        return track

    def _resolve_reference(self, track_name: str, artist_name: str, track_id: Optional[int]) -> Optional[Track]:
        if track_id:
            try:
                return self.deezer_client._to_track(self.deezer_client.get_track(int(track_id)))
            except Exception as e:
                logger.warning(f"Could not load Deezer track {track_id}, falling back to search: {e}")
        return self.deezer_client.find_track(track_name, artist_name)

    def _gather_candidates(self, track_name: str, artist_name: str, similar_artist_limit: int) -> List[Track]:
        """Collect candidates from Last.fm, each with a 0-1 context score."""
        def decay(rank: int) -> float:
            return 1.0 / (1.0 + 0.25 * rank)

        def from_similar_artists() -> List[Track]:
            similar_artists = self.lastfm_client.get_similar_artists(artist_name, similar_artist_limit)
            with ThreadPoolExecutor(max_workers=4) as executor:
                top_tracks = list(executor.map(
                    lambda a: self.lastfm_client.get_artist_top_tracks(a[0], TRACKS_PER_SIMILAR_ARTIST),
                    similar_artists
                ))
            return [
                Track(id=0, title=title, artist_name=artist, context_score=0.8 * match * decay(rank))
                for (_, match), tracks in zip(similar_artists, top_tracks)
                for rank, (title, artist) in enumerate(tracks)
            ]

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_similar = executor.submit(self.lastfm_client.get_similar_tracks, artist_name, track_name)
            future_artists = executor.submit(from_similar_artists)
            future_seed = executor.submit(self.lastfm_client.get_artist_top_tracks, artist_name, SEED_ARTIST_TRACKS_LIMIT)

            seed_artist_tracks = [
                Track(id=0, title=title, artist_name=artist, context_score=0.4 * decay(rank))
                for rank, (title, artist) in enumerate(future_seed.result())
            ]
            return future_similar.result() + future_artists.result() + seed_artist_tracks

    def get_recommendations(self, track_name: str, artist_name: str,
                            recommendations_count: int = FINAL_RECOMMENDATIONS_COUNT,
                            genre: Optional[str] = None,
                            timeframe: Optional[str] = None,
                            track_id: Optional[int] = None,
                            progress_callback: Optional[ProgressCallback] = None) -> RecommendationResult:
        """Find tracks that sound like the reference and that listeners relate to it."""
        progress = progress_callback or ProgressCallback()
        result = RecommendationResult()
        recommendations_count = max(1, min(recommendations_count, MAX_RECOMMENDATIONS_COUNT))
        genre = genre if genre and genre.lower() != 'any' else None
        year_range = parse_timeframe(timeframe)
        filtering = bool(genre or year_range)

        progress.update("Finding reference track...", 5)
        reference = self._resolve_reference(track_name, artist_name, track_id)
        if reference:
            # Use the canonical names Deezer has for the track
            track_name, artist_name = reference.title, reference.artist_name

        progress.update("Fetching similar tracks...", 15)
        # Filters throw away many candidates, so start from a wider net
        candidates = self._gather_candidates(
            track_name, artist_name, SIMILAR_ARTISTS_LIMIT * 2 if filtering else SIMILAR_ARTISTS_LIMIT
        )
        logger.info(f"Found {len(candidates)} candidate tracks")

        candidates = self._filter_tracks(candidates, track_name, artist_name)
        if genre:
            candidates = self._filter_by_genre(candidates, genre)
        if not candidates:
            result.notices.append("We couldn't find any related tracks for this song. Try another one!")
            return result

        # Analyze the most related tracks first, with a cap per artist so the pool stays diverse
        candidates.sort(key=lambda t: t.context_score, reverse=True)
        pool_size = max(MIN_ANALYSIS_POOL, recommendations_count * 4) * (2 if year_range else 1)
        pool = self._diversify(candidates, pool_size, MAX_POOL_TRACKS_PER_ARTIST)

        progress.update("Finding tracks on Deezer...", 30)
        pool = self._resolve_on_deezer(pool)
        if year_range:
            pool = self._filter_by_year(pool, year_range)
        if not pool:
            result.notices.append("None of the related tracks matched your filters. Try setting them to Any.")
            return result

        progress.update("Analyzing audio...", 50)
        with ThreadPoolExecutor(max_workers=6) as executor:
            analyzed = list(executor.map(self.analyze_track, ([reference] if reference else []) + pool))
        if reference:
            reference, pool = analyzed[0], analyzed[1:]
        else:
            pool = analyzed

        progress.update("Calculating similarities...", 90)
        self._score(reference, pool)
        if not (reference and reference.features):
            result.notices.append(
                "We couldn't analyze the audio for this song, so these picks are based on what similar listeners play."
            )

        pool.sort(key=lambda t: t.similarity_score, reverse=True)
        result.tracks = self._diversify(pool, recommendations_count, max_per_artist=1)
        if len(result.tracks) < recommendations_count:
            if filtering:
                result.notices.append(f"Only {len(result.tracks)} tracks matched your filters.")
            # Allow a second track per artist rather than coming up short
            extra = [t for t in pool if t not in result.tracks]
            result.tracks += extra[:recommendations_count - len(result.tracks)]
            result.tracks.sort(key=lambda t: t.similarity_score, reverse=True)

        progress.update("Recommendations complete!", 100)
        logger.info(f"Top {len(result.tracks)} recommendations for '{track_name}' by '{artist_name}':")
        for i, rec in enumerate(result.tracks, 1):
            audio = f"{rec.audio_score:.3f}" if rec.audio_score is not None else "n/a"
            logger.info(f"  {i}. {rec} (score {rec.similarity_score:.3f}, audio {audio}, context {rec.context_score:.3f})")
        return result

    def _score(self, reference: Optional[Track], pool: List[Track]):
        """Blend audio similarity with Last.fm context. Tracks that couldn't be analyzed rank on context alone."""
        max_context = max((t.context_score for t in pool), default=0) or 1.0
        for track in pool:
            track.context_score = track.context_score / max_context

        if not (reference and reference.features):
            for track in pool:
                track.similarity_score = track.context_score
            return

        analyzed = [t for t in pool if t.features is not None]
        audio_scores = self.audio_processor.calculate_advanced_similarity(
            reference.features, [t.features for t in analyzed]
        )
        for track, audio_score in zip(analyzed, audio_scores):
            track.audio_score = audio_score
        for track in pool:
            if track.audio_score is not None:
                track.similarity_score = AUDIO_WEIGHT * track.audio_score + CONTEXT_WEIGHT * track.context_score
            else:
                track.similarity_score = CONTEXT_WEIGHT * track.context_score

    @staticmethod
    def _diversify(tracks: List[Track], limit: int, max_per_artist: int) -> List[Track]:
        """Take tracks in order, allowing at most max_per_artist from any one artist."""
        selected, per_artist = [], {}
        for track in tracks:
            artist = normalize_artist(track.artist_name)
            if per_artist.get(artist, 0) >= max_per_artist:
                continue
            per_artist[artist] = per_artist.get(artist, 0) + 1
            selected.append(track)
            if len(selected) >= limit:
                break
        return selected

    def _filter_tracks(self, tracks: List[Track], reference_title: str, reference_artist: str) -> List[Track]:
        """Drop the reference track, alternate versions and duplicates (keeping the highest score)."""
        reference_title = normalize_title(reference_title)
        best: Dict[Tuple[str, str], Track] = {}
        excluded_count = 0

        for track in tracks:
            title = normalize_title(track.title)
            lowered = track.title.lower()
            if (not title or title == reference_title
                    or is_alternate_version(track.title)
                    or any(word in lowered for word in BLOCKED_TITLE_WORDS)):
                excluded_count += 1
                continue

            key = (title, normalize_artist(track.artist_name))
            if key in best:
                excluded_count += 1
                if track.context_score <= best[key].context_score:
                    continue
            best[key] = track

        logger.info(f"Filtered out {excluded_count} tracks")
        return list(best.values())

    def _filter_by_genre(self, tracks: List[Track], genre: str) -> List[Track]:
        artists = list({t.artist_name for t in tracks})
        with ThreadPoolExecutor(max_workers=6) as executor:
            tags = dict(zip(artists, executor.map(self.lastfm_client.get_artist_tags, artists)))
        filtered = [t for t in tracks if genre_matches(tags.get(t.artist_name, []), genre)]
        logger.info(f"Genre filter '{genre}' kept {len(filtered)} of {len(tracks)} tracks")
        return filtered

    def _filter_by_year(self, tracks: List[Track], year_range: Tuple[int, int]) -> List[Track]:
        with ThreadPoolExecutor(max_workers=6) as executor:
            years = list(executor.map(lambda t: self.deezer_client.release_year(t.id), tracks))
        filtered = []
        for track, year in zip(tracks, years):
            track.release_year = year
            if year and year_range[0] <= year <= year_range[1]:
                filtered.append(track)
        logger.info(f"Timeframe filter {year_range} kept {len(filtered)} of {len(tracks)} tracks")
        return filtered

    def _resolve_on_deezer(self, tracks: List[Track]) -> List[Track]:
        """Attach Deezer IDs, previews and covers; drop tracks Deezer doesn't have."""
        with ThreadPoolExecutor(max_workers=6) as executor:
            found = list(executor.map(lambda t: self.deezer_client.find_track(t.title, t.artist_name), tracks))
        resolved = []
        for track, deezer_track in zip(tracks, found):
            if deezer_track:
                track.id = deezer_track.id
                track.preview_url = deezer_track.preview_url
                track.album_cover = deezer_track.album_cover
                resolved.append(track)
            else:
                logger.debug(f"Could not find on Deezer: {track}")
        logger.info(f"Found {len(resolved)} of {len(tracks)} tracks on Deezer")
        return resolved


# Utility functions
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
    query = f"{clean_track_name(track_name)} {clean_artist_name(artist_name)}"
    return f"https://open.spotify.com/search/{urllib.parse.quote(query)}"

def get_apple_music_search_link(track_name: str, artist_name: str) -> str:
    """Generates an Apple Music search link for the given track and artist."""
    query = f"{clean_track_name(track_name)} {clean_artist_name(artist_name)}"
    return f"https://music.apple.com/us/search?term={urllib.parse.quote(query)}"

def main():
    def progress_handler(message: str, progress: int):
        """Simple progress handler for console output"""
        print(f"[{progress:3d}%] {message}")

    track_name = input("Enter the track name: ")
    artist_name = input("Enter the artist name: ")

    recommender = MusicRecommender()
    result = recommender.get_recommendations(
        track_name, artist_name,
        progress_callback=ProgressCallback(progress_handler)
    )

    for notice in result.notices:
        print(f"Note: {notice}")
    if result.tracks:
        print(f"\nTop {len(result.tracks)} Recommendations for '{track_name}' by '{artist_name}':")
        for i, rec in enumerate(result.tracks, start=1):
            print(f"{i}. {rec} (Similarity Score: {rec.similarity_score * 100:.2f}%)")
            print(f"   Spotify: {get_spotify_search_link(rec.title, rec.artist_name)}")
            print(f"   Apple Music: {get_apple_music_search_link(rec.title, rec.artist_name)}")
            print()
    else:
        print("No recommendations found. Please try a different track or artist.")

if __name__ == "__main__":
    main()
