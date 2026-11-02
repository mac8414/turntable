"""Scoring shared by every experiment. Only needs numpy so it works in any model's environment."""
import json
import os
from collections import Counter, defaultdict

import numpy as np

CACHE_DIR = os.path.join(os.path.dirname(__file__), '.cache')
AUDIO_DIR = os.path.join(CACHE_DIR, 'audio')
TRACKS_PATH = os.path.join(CACHE_DIR, 'tracks.json')
TOP_K = 5


def load_tracks():
    """Tracks written by genre_eval.py: genre, artist, title, deezer_id."""
    with open(TRACKS_PATH) as f:
        return json.load(f)


def audio_path(track):
    return os.path.join(AUDIO_DIR, f"{track['deezer_id']}.mp3")


def cosine_matrix(vectors):
    vectors = np.asarray(vectors, dtype=float)
    vectors = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12)
    return vectors @ vectors.T


def evaluate(tracks, sims):
    """Mean precision@K and nearest-neighbor accuracy, ignoring same-artist neighbors."""
    precisions, nn_hits = [], []
    confusion = defaultdict(Counter)
    per_genre = defaultdict(list)
    for i, query in enumerate(tracks):
        candidates = [j for j in range(len(tracks)) if tracks[j]['artist'] != query['artist']]
        ranked = sorted(candidates, key=lambda j: sims[i, j], reverse=True)[:TOP_K]
        hits = [tracks[j]['genre'] == query['genre'] for j in ranked]
        precisions.append(np.mean(hits))
        nn_hits.append(hits[0])
        per_genre[query['genre']].append(np.mean(hits))
        for j in ranked:
            confusion[query['genre']][tracks[j]['genre']] += 1
    return np.mean(precisions), np.mean(nn_hits), per_genre, confusion


def random_baseline(tracks):
    expected = []
    for query in tracks:
        others = [t for t in tracks if t['artist'] != query['artist']]
        expected.append(sum(t['genre'] == query['genre'] for t in others) / len(others))
    return np.mean(expected)


def print_row(name, precision, nn=None):
    nn_text = f"{nn:.2f}" if nn is not None else ""
    print(f"{name:32s} {precision:.2f}           {nn_text}")


def print_header():
    print(f"{'method':32s} precision@{TOP_K}   nearest-neighbor")


def print_genre_breakdown(tracks, per_genre, confusion):
    print(f"\nBy genre (precision@{TOP_K}) and what each genre is confused with:")
    for genre in dict.fromkeys(t['genre'] for t in tracks):
        wrong = [(g, c) for g, c in confusion[genre].most_common() if g != genre][:2]
        wrong_text = ', '.join(f"{g} ({c})" for g, c in wrong)
        print(f"  {genre:12s} {np.mean(per_genre[genre]):.2f}   confused with: {wrong_text}")
