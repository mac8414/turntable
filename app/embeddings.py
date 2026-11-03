"""
How songs sound, as numbers. Discogs-EffNet (a model trained to recognize ~400 music styles) turns a
30 second preview into 1280 numbers; songs that sound alike get similar numbers. SongCatalog keeps
every song we've embedded on disk so it can be searched for sound-alikes and never analyzed twice.
"""
import json
import logging
import os
import tempfile
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional, Tuple

import numpy as np
import requests

logger = logging.getLogger(__name__)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(APP_DIR, 'models', 'discogs-effnet-bs64-1.pb')
MODEL_URL = 'https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb'
CATALOG_DIR = os.path.join(APP_DIR, 'data')
EMBEDDING_SIZE = 1280
SAMPLE_RATE = 16000
# The model always runs a batch of 64 patches (~2s each, 1s apart), costing ~370 ms however much
# audio it gets. A 15s clip is 14 patches, so 4 songs fit in one run: ~95 ms per song instead of
# ~370. 15s clips score the same as full 30s previews (see experiments/README.md).
CLIP_SAMPLES = 15 * SAMPLE_RATE
SONGS_PER_RUN = 4
FRAME_HOP, PATCH_FRAMES, PATCH_HOP_FRAMES = 256, 128, 62


def ensure_model() -> str:
    """Download the 18 MB model the first time the app runs."""
    if not os.path.exists(MODEL_PATH):
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        logger.info("Downloading Discogs-EffNet model (18 MB)...")
        partial = MODEL_PATH + '.part'
        urllib.request.urlretrieve(MODEL_URL, partial)
        os.replace(partial, MODEL_PATH)
    return MODEL_PATH


def _unit(vectors: np.ndarray) -> np.ndarray:
    return vectors / (np.linalg.norm(vectors, axis=-1, keepdims=True) + 1e-12)


class EffnetEmbedder:
    """Turns a song preview into a 1280-number description of how it sounds."""

    def __init__(self):
        import essentia
        from essentia.standard import MonoLoader, TensorflowPredictEffnetDiscogs
        essentia.log.infoActive = False
        essentia.log.warningActive = False
        self._loader = MonoLoader
        self._model_class = TensorflowPredictEffnetDiscogs
        self._graph = ensure_model()
        self._local = threading.local()

    def _model(self):
        # Essentia algorithms aren't thread-safe, so each worker thread gets its own copy
        if not hasattr(self._local, 'model'):
            self._local.model = self._model_class(graphFilename=self._graph, output='PartitionedCall:1')
        return self._local.model

    def _middle_clip(self, path: str) -> Optional[np.ndarray]:
        audio = self._loader(filename=path, sampleRate=SAMPLE_RATE, resampleQuality=4)()
        if len(audio) < 3 * SAMPLE_RATE:  # too short for the model's ~2 second patches
            return None
        start = max(0, (len(audio) - CLIP_SAMPLES) // 2)
        clip = audio[start:start + CLIP_SAMPLES]
        return np.pad(clip, (0, CLIP_SAMPLES - len(clip)))

    def _embed_clips(self, clips: List[np.ndarray]) -> List[np.ndarray]:
        """Run several equal-length clips through the model at once and split the patches back out."""
        patches = self._model()(np.concatenate(clips))
        per_clip = [[] for _ in clips]
        for i, patch in enumerate(patches):
            first = PATCH_HOP_FRAMES * i * FRAME_HOP
            last = (PATCH_HOP_FRAMES * i + PATCH_FRAMES) * FRAME_HOP - 1
            # Skip patches that straddle two songs
            if first // CLIP_SAMPLES == last // CLIP_SAMPLES < len(clips):
                per_clip[first // CLIP_SAMPLES].append(patch)
        # One embedding per patch; average them into one description of the song
        return [np.mean(p, axis=0).astype(np.float32) for p in per_clip]

    def embed_files(self, paths: List[str]) -> List[Optional[np.ndarray]]:
        clips = []
        for path in paths:
            try:
                clips.append(self._middle_clip(path))
            except Exception as e:
                logger.warning(f"Could not decode {path}: {e}")
                clips.append(None)
        valid = [i for i, clip in enumerate(clips) if clip is not None]
        results: List[Optional[np.ndarray]] = [None] * len(paths)
        for start in range(0, len(valid), SONGS_PER_RUN):
            group = valid[start:start + SONGS_PER_RUN]
            for i, embedding in zip(group, self._embed_clips([clips[i] for i in group])):
                results[i] = embedding
        return results

    def embed_urls(self, urls: List[Optional[str]]) -> List[Optional[np.ndarray]]:
        """Download previews in parallel and embed them in packed batches. None where a preview failed."""
        with ThreadPoolExecutor(max_workers=6) as executor:
            paths = list(executor.map(_download, urls))
        try:
            found = [i for i, path in enumerate(paths) if path]
            embeddings = self.embed_files([paths[i] for i in found])
            results: List[Optional[np.ndarray]] = [None] * len(urls)
            for i, embedding in zip(found, embeddings):
                results[i] = embedding
            return results
        finally:
            for path in paths:
                if path:
                    os.remove(path)

    def embed_url(self, url: Optional[str]) -> Optional[np.ndarray]:
        return self.embed_urls([url])[0]


def _download(url: Optional[str]) -> Optional[str]:
    """Save a preview to a temp file; None if it can't be fetched."""
    if not url:
        return None
    try:
        response = requests.get(url, timeout=15, headers={"Referer": "https://www.deezer.com"})
        if response.status_code != 200 or len(response.content) < 10 * 1024:
            return None
        handle, path = tempfile.mkstemp(suffix='.mp3')
        with os.fdopen(handle, 'wb') as f:
            f.write(response.content)
        return path
    except Exception as e:
        logger.warning(f"Could not download {url[:60]}...: {e}")
        return None


class SongCatalog:
    """
    Songs with their embeddings, saved to app/data. Songs are dicts with deezer_id, title, artist,
    cover and optionally release_year. Look up by Deezer ID or by a caller-provided name key.
    """

    def __init__(self, directory: str = CATALOG_DIR, key_fn: Optional[Callable[[str, str], str]] = None):
        self.meta_path = os.path.join(directory, 'catalog.json')
        self.vectors_path = os.path.join(directory, 'catalog_embeddings.npy')
        self._key_fn = key_fn or (lambda title, artist: f"{title.lower()}|{artist.lower()}")
        self._lock = threading.RLock()
        self._dirty = False

        self.songs: List[dict] = []
        vectors = np.zeros((0, EMBEDDING_SIZE), dtype=np.float32)
        if os.path.exists(self.meta_path) and os.path.exists(self.vectors_path):
            with open(self.meta_path) as f:
                self.songs = json.load(f)
            vectors = np.load(self.vectors_path).astype(np.float32)
            if len(vectors) != len(self.songs):
                logger.error("Catalog files are out of sync; starting with an empty catalog")
                self.songs, vectors = [], np.zeros((0, EMBEDDING_SIZE), dtype=np.float32)
        self._vectors = vectors
        self._by_id = {song['deezer_id']: i for i, song in enumerate(self.songs)}
        self._by_key = {self._key_fn(song['title'], song['artist']): i for i, song in enumerate(self.songs)}
        self._search_matrix = None
        logger.info(f"Loaded song catalog with {len(self.songs)} songs")

    def __len__(self):
        return len(self.songs)

    def get(self, deezer_id: int) -> Optional[Tuple[dict, np.ndarray]]:
        with self._lock:
            index = self._by_id.get(deezer_id)
            return None if index is None else (self.songs[index], self._vectors[index])

    def find(self, title: str, artist: str) -> Optional[Tuple[dict, np.ndarray]]:
        with self._lock:
            index = self._by_key.get(self._key_fn(title, artist))
            return None if index is None else (self.songs[index], self._vectors[index])

    def add(self, song: dict, vector: np.ndarray):
        with self._lock:
            if song['deezer_id'] in self._by_id:
                return
            self._by_id[song['deezer_id']] = len(self.songs)
            self._by_key.setdefault(self._key_fn(song['title'], song['artist']), len(self.songs))
            self.songs.append(song)
            self._vectors = np.vstack([self._vectors, vector.astype(np.float32)[None, :]])
            self._search_matrix = None
            self._dirty = True

    def update(self, deezer_id: int, **fields):
        with self._lock:
            index = self._by_id.get(deezer_id)
            if index is not None:
                self.songs[index].update(fields)
                self._dirty = True

    def _matrix(self):
        """Embeddings centered on the catalog average and scaled to length 1, for cosine similarity."""
        with self._lock:
            if self._search_matrix is None:
                mean = self._vectors.mean(axis=0) if len(self._vectors) > 1 else np.zeros(EMBEDDING_SIZE)
                self._search_matrix = (_unit(self._vectors - mean), mean)
            return self._search_matrix

    def similarity(self, query: np.ndarray, others: List[np.ndarray]) -> np.ndarray:
        """Cosine similarity after centering, which separates songs better than raw cosine."""
        _, mean = self._matrix()
        return _unit(np.asarray(others) - mean) @ _unit(query - mean)

    def nearest(self, query: np.ndarray, limit: int, skip: Callable[[dict], bool] = lambda song: False
                ) -> List[Tuple[float, dict, np.ndarray]]:
        """The `limit` songs that sound most like `query`, best first."""
        matrix, mean = self._matrix()
        if not len(matrix):
            return []
        scores = matrix @ _unit(query - mean)
        results = []
        for index in np.argsort(scores)[::-1]:
            if not skip(self.songs[index]):
                results.append((float(scores[index]), self.songs[index], self._vectors[index]))
                if len(results) >= limit:
                    break
        return results

    def save(self):
        with self._lock:
            if not self._dirty:
                return
            os.makedirs(os.path.dirname(self.meta_path), exist_ok=True)
            # Write to temp files then swap, so a crash can't leave the two files out of sync
            with open(self.meta_path + '.tmp', 'w') as f:
                json.dump(self.songs, f)
            with open(self.vectors_path + '.tmp.npy', 'wb') as f:
                np.save(f, self._vectors)
            os.replace(self.vectors_path + '.tmp.npy', self.vectors_path)
            os.replace(self.meta_path + '.tmp', self.meta_path)
            self._dirty = False
