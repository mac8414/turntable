"""
Step 4: MERT (m-a-p), a large self-supervised music model from research. It isn't trained on
labels; it learns music structure from raw audio. Each layer captures something different
(low layers: timbre and sound, higher layers: more abstract structure), so every layer is scored.

Needs torch, transformers, nnAudio, librosa and the cached previews from genre_eval.py.
Downloads and runs model code from the m-a-p Hugging Face repo (trust_remote_code).
Run from the project root:  python experiments/mert_eval.py   (MERT_MODEL=m-a-p/MERT-v1-330M for the large one)
"""
import os
import time

import librosa
import numpy as np
import torch
from transformers import AutoModel, Wav2Vec2FeatureExtractor

from evaluation import (
    CACHE_DIR, audio_path, cosine_matrix, evaluate, load_tracks, print_genre_breakdown,
    print_header, print_row, random_baseline,
)

MODEL_ID = os.getenv('MERT_MODEL', 'm-a-p/MERT-v1-95M')
DEVICE = os.getenv('MERT_DEVICE', 'cpu')
CHUNK_SECONDS = 10


def main():
    t0 = time.perf_counter()
    model = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True).to(DEVICE).eval()
    processor = Wav2Vec2FeatureExtractor.from_pretrained(MODEL_ID, trust_remote_code=True)
    model_load = time.perf_counter() - t0
    sample_rate = processor.sampling_rate
    params = sum(p.numel() for p in model.parameters()) / 1e6

    tracks = load_tracks()
    layer_embeddings, decode_times, embed_times = [], [], []
    with torch.no_grad():
        for track in tracks:
            t0 = time.perf_counter()
            audio, _ = librosa.load(audio_path(track), sr=sample_rate, mono=True)
            chunk = sample_rate * CHUNK_SECONDS
            chunks = [audio[i:i + chunk] for i in range(0, len(audio) - chunk // 2, chunk)] or [audio]
            t1 = time.perf_counter()
            per_chunk = []
            for piece in chunks:
                inputs = processor(piece, sampling_rate=sample_rate, return_tensors='pt')
                inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
                hidden = model(**inputs, output_hidden_states=True).hidden_states
                # (layers, features): average each layer over time
                per_chunk.append(torch.stack(hidden).squeeze(1).mean(dim=1).cpu().numpy())
            layer_embeddings.append(np.mean(per_chunk, axis=0))
            decode_times.append(t1 - t0)
            embed_times.append(time.perf_counter() - t1)

    layer_embeddings = np.array(layer_embeddings)  # (tracks, layers, features)
    np.save(os.path.join(CACHE_DIR, f"mert_{MODEL_ID.split('/')[-1]}.npy"), layer_embeddings)

    print(f"\n{MODEL_ID}: {params:.0f}M parameters, loaded in {model_load:.1f}s on {DEVICE}. "
          f"Per 30s preview: decode {np.mean(decode_times) * 1000:.0f} ms, "
          f"embedding {np.mean(embed_times) * 1000:.0f} ms\n")

    print_header()
    print_row('random guessing', random_baseline(tracks))
    results = []
    for layer in range(layer_embeddings.shape[1]):
        p, nn, per_genre, confusion = evaluate(tracks, cosine_matrix(layer_embeddings[:, layer]))
        results.append((p, nn, layer, per_genre, confusion))
        print_row(f'  layer {layer}', p, nn)

    # Standardize each layer's features before averaging so no single layer dominates
    standardized = (layer_embeddings - layer_embeddings.mean(axis=0)) / (layer_embeddings.std(axis=0) + 1e-6)
    print_row('all layers averaged', *evaluate(tracks, cosine_matrix(standardized.mean(axis=1)))[:2])

    p, nn, layer, per_genre, confusion = max(results, key=lambda r: r[0])
    print(f"\nBest single layer: {layer} ({p:.2f})")
    print_genre_breakdown(tracks, per_genre, confusion)


if __name__ == '__main__':
    main()
