"""
Minimal Deezer/Last.fm/Discogs-EffNet helpers for experiments that run outside the app's
environment (essentia-tensorflow can't share one with librosa). Only needs requests, numpy, essentia.
"""
import json
import os
import re
import tempfile
import threading
import time
import unicodedata

import numpy as np
import requests

from evaluation import CACHE_DIR

LASTFM_URL = 'https://ws.audioscrobbler.com/2.0/'
DEEZER_URL = 'https://api.deezer.com'


def _load_lastfm_key():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    with open(env_path) as f:
        for line in f:
            name, _, value = line.partition('=')
            if name.strip() == 'LASTFM_API_KEY':
                return value.strip()
    raise RuntimeError('LASTFM_API_KEY missing from .env')


LASTFM_API_KEY = _load_lastfm_key()


def normalize_artist(name):
    name = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    name = re.sub(r'[^\w\s]', '', name.lower().replace('&', 'and'))
    return re.sub(r'^the\s+', '', re.sub(r'\s+', ' ', name)).strip()


class _RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls, self.period, self.calls, self.lock = max_calls, period, [], threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            self.calls = [t for t in self.calls if now - t < self.period]
            if len(self.calls) >= self.max_calls:
                time.sleep(self.period - (now - self.calls[0]))
            self.calls.append(time.monotonic())


_deezer_limit = _RateLimiter(45, 5.0)
_lastfm_limit = _RateLimiter(20, 4.0)


def deezer(path, **params):
    for attempt in range(4):
        _deezer_limit.wait()
        try:
            data = requests.get(f'{DEEZER_URL}/{path}', params=params, timeout=10).json()
        except (requests.RequestException, ValueError):
            time.sleep(1)
            continue
        if isinstance(data, dict) and data.get('error', {}).get('code') == 4:  # quota exceeded
            time.sleep(2)
            continue
        return data
    return {}


def lastfm(method, **params):
    _lastfm_limit.wait()
    params.update(method=method, api_key=LASTFM_API_KEY, format='json', autocorrect=1)
    try:
        data = requests.get(LASTFM_URL, params=params, timeout=10).json()
    except (requests.RequestException, ValueError):
        return {}
    return {} if 'error' in data else data


def find_on_deezer(title, artist):
    """First Deezer result by this artist that has a preview: {deezer_id, title, artist, preview, cover}."""
    results = deezer('search', q=f'{artist} {title}', limit=10).get('data', [])
    wanted = normalize_artist(artist)
    for r in results:
        if r.get('preview') and normalize_artist(r['artist']['name']) == wanted:
            return {'deezer_id': r['id'], 'title': r['title'], 'artist': r['artist']['name'],
                    'preview': r['preview'], 'cover': r['album'].get('cover_medium')}
    return None


def fresh_preview(deezer_id):
    """Preview URLs expire, so look them up right before downloading."""
    return deezer(f'track/{deezer_id}').get('preview')


def download(url):
    if not url:
        return None
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200 or len(response.content) < 10_000:
            return None
    except requests.RequestException:
        return None
    handle, path = tempfile.mkstemp(suffix='.mp3')
    with os.fdopen(handle, 'wb') as f:
        f.write(response.content)
    return path


class JsonCache:
    """Dict persisted to experiments/.cache/<name>.json."""
    def __init__(self, name):
        self.path = os.path.join(CACHE_DIR, f'{name}.json')
        self.data = json.load(open(self.path)) if os.path.exists(self.path) else {}

    def get_or_compute(self, key, compute):
        if key not in self.data:
            self.data[key] = compute()
        return self.data[key]

    def save(self):
        with open(self.path, 'w') as f:
            json.dump(self.data, f)


_artist_tags = JsonCache('lastfm_artist_tags')
_similar_artists = JsonCache('lastfm_similar_artists')


def artist_tags(artist):
    def fetch():
        tags = lastfm('artist.getTopTags', artist=artist).get('toptags', {}).get('tag', [])
        return [t['name'].lower() for t in tags[:8]]
    return _artist_tags.get_or_compute(artist.lower(), fetch)


def similar_artists(artist, limit=100):
    def fetch():
        artists = lastfm('artist.getSimilar', artist=artist, limit=limit).get('similarartists', {}).get('artist', [])
        return [normalize_artist(a['name']) for a in artists]
    return _similar_artists.get_or_compute(artist.lower(), fetch)


def save_lastfm_caches():
    _artist_tags.save()
    _similar_artists.save()


class EffnetEmbedder:
    """Discogs-EffNet song embedding (1280 numbers), averaged over the preview."""
    def __init__(self):
        from essentia.standard import MonoLoader, TensorflowPredictEffnetDiscogs  # noqa: F401
        self._loader = MonoLoader
        graph = os.path.join(CACHE_DIR, 'models', 'discogs-effnet-bs64-1.pb')
        self._model = TensorflowPredictEffnetDiscogs(graphFilename=graph, output='PartitionedCall:1')

    def embed_file(self, path):
        audio = self._loader(filename=path, sampleRate=16000, resampleQuality=4)()
        return self._model(audio).mean(axis=0)

    def embed_url(self, url):
        path = download(url)
        if not path:
            return None
        try:
            return self.embed_file(path)
        except Exception:
            return None
        finally:
            os.remove(path)


def normalize_rows(x):
    x = np.asarray(x, dtype=np.float32)
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-12)
