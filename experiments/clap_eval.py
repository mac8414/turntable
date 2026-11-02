"""
Step 3: CLAP (LAION, music checkpoint), a model trained to put audio and text descriptions
in the same space. Besides song-to-song similarity, it tests whether plain text could have
powered the Genre knob ("a jazz song") or a free-text search ("calm piano music").

Needs torch, transformers, librosa and the cached previews from genre_eval.py.
Run from the project root:  python experiments/clap_eval.py
(CLAP_MODEL=<hugging face id> to pick a checkpoint, CLAP_DEVICE=mps to use the Mac GPU)
"""
import os
import time

import librosa
import numpy as np
import torch
from transformers import ClapModel, ClapProcessor

from evaluation import (
    CACHE_DIR, audio_path, cosine_matrix, evaluate, load_tracks, print_genre_breakdown,
    print_header, print_row, random_baseline,
)

# laion/larger_clap_music is broken on Hugging Face: every text prompt gets almost the same embedding
MODEL_ID = os.getenv('CLAP_MODEL', 'laion/larger_clap_general')
SAMPLE_RATE = 48000
CHUNK_SECONDS = 10  # CLAP looks at 10 second windows; a 30s preview becomes 3 chunks
DEVICE = os.getenv('CLAP_DEVICE', 'cpu')

GENRE_PROMPTS = {
    'rock': 'rock music', 'metal': 'heavy metal music', 'hip-hop': 'hip-hop music',
    'electronic': 'electronic dance music', 'jazz': 'jazz music', 'classical': 'classical music',
    'country': 'country music', 'r&b/soul': 'r&b and soul music', 'reggae': 'reggae music',
    'folk': 'acoustic folk music',
}
SEARCH_QUERIES = [
    'fast aggressive distorted guitars',
    'calm solo piano',
    '1970s soul with horns',
    'drum machine and synthesizers',
    'a man singing with an acoustic guitar',
]


def normalize(x):
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-12)


def call_processor(processor, audio_chunks):
    # The keyword changed from `audios` to `audio` across transformers versions
    try:
        return processor(audio=audio_chunks, sampling_rate=SAMPLE_RATE, return_tensors='pt')
    except TypeError:
        return processor(audios=audio_chunks, sampling_rate=SAMPLE_RATE, return_tensors='pt')


def as_array(features):
    # Newer transformers versions return a model output object instead of a tensor
    if not torch.is_tensor(features):
        pooled = getattr(features, 'pooler_output', None)
        features = pooled if pooled is not None else features[0]
    return features.cpu().numpy()


def main():
    t0 = time.perf_counter()
    model = ClapModel.from_pretrained(MODEL_ID).to(DEVICE).eval()
    processor = ClapProcessor.from_pretrained(MODEL_ID)
    model_load = time.perf_counter() - t0
    params = sum(p.numel() for p in model.parameters()) / 1e6

    tracks = load_tracks()
    embeddings, decode_times, embed_times = [], [], []
    with torch.no_grad():
        for track in tracks:
            t0 = time.perf_counter()
            audio, _ = librosa.load(audio_path(track), sr=SAMPLE_RATE, mono=True)
            chunk = SAMPLE_RATE * CHUNK_SECONDS
            chunks = [audio[i:i + chunk] for i in range(0, len(audio) - chunk // 2, chunk)] or [audio]
            t1 = time.perf_counter()
            inputs = {k: v.to(DEVICE) for k, v in call_processor(processor, chunks).items()}
            chunk_embeddings = as_array(model.get_audio_features(**inputs))
            embeddings.append(normalize(normalize(chunk_embeddings).mean(axis=0)))
            decode_times.append(t1 - t0)
            embed_times.append(time.perf_counter() - t1)

        def embed_text(texts):
            inputs = processor(text=texts, return_tensors='pt', padding=True)
            inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
            return normalize(as_array(model.get_text_features(**inputs)))

        genre_names = list(GENRE_PROMPTS)
        genre_text = embed_text(list(GENRE_PROMPTS.values()))
        query_text = embed_text(SEARCH_QUERIES)

    embeddings = np.array(embeddings)
    np.save(os.path.join(CACHE_DIR, f"clap_{MODEL_ID.split('/')[-1]}.npy"), embeddings)

    print(f"\n{MODEL_ID}: {params:.0f}M parameters, loaded in {model_load:.1f}s on {DEVICE}. "
          f"Per 30s preview: decode {np.mean(decode_times) * 1000:.0f} ms, "
          f"embedding {np.mean(embed_times) * 1000:.0f} ms\n")

    print_header()
    print_row('random guessing', random_baseline(tracks))
    p, nn, per_genre, confusion = evaluate(tracks, cosine_matrix(embeddings))
    print_row('clap embeddings', p, nn)
    print_genre_breakdown(tracks, per_genre, confusion)

    # Zero-shot: pick the genre whose text description is closest to the audio
    predicted = [genre_names[i] for i in np.argmax(embeddings @ genre_text.T, axis=1)]
    accuracy = np.mean([p == t['genre'] for p, t in zip(predicted, tracks)])
    print(f"\nText-only genre labeling ('{GENRE_PROMPTS['jazz']}', ...): {accuracy:.0%} correct "
          f"(random would be {1 / len(genre_names):.0%})")

    print("\nFree-text search, top 3 songs:")
    for query, scores in zip(SEARCH_QUERIES, query_text @ embeddings.T):
        top = np.argsort(scores)[::-1][:3]
        found = '; '.join(f"{tracks[i]['title']} ({tracks[i]['artist']})" for i in top)
        print(f"  \"{query}\"\n      -> {found}")


if __name__ == '__main__':
    main()
