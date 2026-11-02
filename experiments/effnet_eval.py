"""
Step 2: Discogs-EffNet (Essentia), a model trained to recognize ~400 music styles from audio.

Tests two ways of comparing songs with it:
  - embeddings: the model's internal 1280-number description of the sound
  - styles: its 400 style probabilities ("Electronic---French House": 0.8, ...)

Needs essentia-tensorflow (pip install essentia-tensorflow) and the cached previews from genre_eval.py.
Run from the project root:  python experiments/effnet_eval.py
"""
import os
import time
import urllib.request

import json
import numpy as np
from essentia.standard import MonoLoader, TensorflowPredictEffnetDiscogs

from evaluation import (
    CACHE_DIR, audio_path, cosine_matrix, evaluate, load_tracks, print_genre_breakdown,
    print_header, print_row, random_baseline,
)

MODEL_DIR = os.path.join(CACHE_DIR, 'models')
MODEL_URL = 'https://essentia.upf.edu/models/feature-extractors/discogs-effnet/'
MODEL_NAME = 'discogs-effnet-bs64-1'


def download_model():
    os.makedirs(MODEL_DIR, exist_ok=True)
    for ext in ('pb', 'json'):
        path = os.path.join(MODEL_DIR, f'{MODEL_NAME}.{ext}')
        if not os.path.exists(path):
            urllib.request.urlretrieve(f'{MODEL_URL}{MODEL_NAME}.{ext}', path)
    with open(os.path.join(MODEL_DIR, f'{MODEL_NAME}.json')) as f:
        return json.load(f)['classes']


def main():
    styles = download_model()
    graph = os.path.join(MODEL_DIR, f'{MODEL_NAME}.pb')

    t0 = time.perf_counter()
    embedder = TensorflowPredictEffnetDiscogs(graphFilename=graph, output='PartitionedCall:1')
    classifier = TensorflowPredictEffnetDiscogs(graphFilename=graph, output='PartitionedCall:0')
    model_load = time.perf_counter() - t0

    tracks = load_tracks()
    embeddings, style_probs, decode_times, embed_times = [], [], [], []
    for track in tracks:
        t0 = time.perf_counter()
        audio = MonoLoader(filename=audio_path(track), sampleRate=16000, resampleQuality=4)()
        t1 = time.perf_counter()
        # The model looks at ~3 second patches; average them into one description per song
        embeddings.append(embedder(audio).mean(axis=0))
        t2 = time.perf_counter()
        style_probs.append(classifier(audio).mean(axis=0))
        decode_times.append(t1 - t0)
        embed_times.append(t2 - t1)

    np.save(os.path.join(CACHE_DIR, 'effnet_embeddings.npy'), np.array(embeddings))

    print(f"\nModel load {model_load:.1f}s. Per 30s preview: decode {np.mean(decode_times) * 1000:.0f} ms, "
          f"embedding {np.mean(embed_times) * 1000:.0f} ms\n")

    print_header()
    print_row('random guessing', random_baseline(tracks))
    p, nn, per_genre, confusion = evaluate(tracks, cosine_matrix(embeddings))
    print_row('effnet embeddings', p, nn)
    print_row('effnet style probabilities', *evaluate(tracks, cosine_matrix(style_probs))[:2])
    print_genre_breakdown(tracks, per_genre, confusion)

    print("\nWhat the model hears (top 2 styles) for a few songs:")
    for i in range(0, len(tracks), 9):
        top = np.argsort(style_probs[i])[::-1][:2]
        heard = ', '.join(f"{styles[j]} ({style_probs[i][j]:.2f})" for j in top)
        print(f"  {tracks[i]['title'][:22]:22s} {tracks[i]['artist'][:18]:18s} -> {heard}")


if __name__ == '__main__':
    main()
