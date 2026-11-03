"""
Step 5c: compare four ways to recommend 5 songs for each seed:

  A. app        - the shipped app: Last.fm shortlist reranked with librosa (from app_recs.py)
  B. shortlist  - the same Last.fm shortlist reranked with Discogs-EffNet
  C. catalog    - nearest sound-alikes in the whole EffNet catalog, ignoring Last.fm
  D. hybrid     - shortlist + catalog neighbors scored together

Measures (each favors different methods, so read them together):
  genre      - recommendation's artist has Last.fm tags matching the seed's genre (independent of EffNet)
  related    - artist is among Last.fm's 100 most similar artists to the seed artist (favors A, B, D)
  sound      - EffNet similarity to the seed (favors B, C, D)
  seconds    - cold latency for one request

Needs essentia-tensorflow and the outputs of catalog_build.py and app_recs.py.
Run from the project root:  python experiments/catalog_eval.py
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from evaluation import CACHE_DIR
from sources import (
    EffnetEmbedder, artist_tags, download, fresh_preview, normalize_artist, normalize_rows,
    save_lastfm_caches, similar_artists,
)

RECOMMENDATIONS = 5
CATALOG_NEIGHBORS = 40
AUDIO_WEIGHT, CONTEXT_WEIGHT = 0.65, 0.35  # same blend as the app

GENRE_TAGS = {
    'rock': ['rock', 'grunge', 'punk', 'alternative', 'britpop', 'shoegaze'],
    'metal': ['metal', 'metalcore', 'thrash'],
    'hip-hop': ['hip-hop', 'hip hop', 'hiphop', 'rap', 'trap'],
    'electronic': ['electronic', 'electronica', 'edm', 'house', 'techno', 'trance', 'ambient', 'idm', 'dance',
                   'progressive house', 'synthpop'],
    'jazz': ['jazz', 'bebop', 'swing', 'fusion'],
    'classical': ['classical', 'orchestral', 'baroque', 'opera', 'composer', 'piano', 'romantic', 'impressionism'],
    'country': ['country', 'americana', 'bluegrass', 'honky tonk'],
    'r&b/soul': ['r&b', 'rnb', 'soul', 'funk', 'motown'],
    'reggae': ['reggae', 'dub', 'ska', 'dancehall', 'roots'],
    'folk': ['folk', 'singer-songwriter', 'acoustic', 'americana'],
}


class EmbeddingStore:
    """EffNet embeddings for individual Deezer tracks, cached on disk."""
    def __init__(self, embedder):
        self.embedder = embedder
        self.path = os.path.join(CACHE_DIR, 'track_embeddings.npz')
        self.cache = dict(np.load(self.path)) if os.path.exists(self.path) else {}

    def embed_many(self, deezer_ids):
        """Returns {id: embedding} and the wall time a cold request would have spent."""
        missing = [i for i in dict.fromkeys(deezer_ids) if i and str(i) not in self.cache]
        t0 = time.perf_counter()
        # Downloads in parallel, the model one song at a time (as the app would)
        with ThreadPoolExecutor(max_workers=6) as executor:
            for deezer_id, path in zip(missing, executor.map(lambda i: download(fresh_preview(i)), missing)):
                if path:
                    try:
                        self.cache[str(deezer_id)] = self.embedder.embed_file(path)
                    finally:
                        os.remove(path)
        seconds = time.perf_counter() - t0
        np.savez(self.path, **self.cache)
        return {i: self.cache[str(i)] for i in deezer_ids if i and str(i) in self.cache}, seconds


def genre_match(artist, genre):
    tags = artist_tags(artist)
    return any(keyword in tag for tag in tags for keyword in GENRE_TAGS[genre])


def pick_diverse(scored, seed_artist, seed_title):
    """Top songs, one per artist, skipping the seed itself."""
    picked, artists = [], set()
    for score, item in sorted(scored, key=lambda s: s[0], reverse=True):
        artist = normalize_artist(item['artist'])
        is_seed = artist == normalize_artist(seed_artist) and item['title'].lower().startswith(seed_title.lower())
        if artist in artists or is_seed:
            continue
        artists.add(artist)
        picked.append(item)
        if len(picked) == RECOMMENDATIONS:
            break
    return picked


def rescale(values):
    values = np.asarray(values, dtype=float)
    spread = values.max() - values.min() if len(values) else 0
    return (values - values.min()) / spread if spread > 0 else np.zeros_like(values)


def main():
    catalog = json.load(open(os.path.join(CACHE_DIR, 'catalog.json')))
    catalog_vectors = np.load(os.path.join(CACHE_DIR, 'catalog_embeddings.npy'))
    # Center on the catalog average, which measurably helps cosine similarity (see README)
    catalog_mean = catalog_vectors.mean(axis=0)
    center = lambda x: normalize_rows(np.asarray(x) - catalog_mean)
    catalog_unit = center(catalog_vectors)
    seeds = json.load(open(os.path.join(CACHE_DIR, 'app_recs.json')))
    store = EmbeddingStore(EffnetEmbedder())
    print(f"Catalog: {len(catalog)} songs\n")

    totals = {m: {'genre': [], 'related': [], 'sound': [], 'seconds': []} for m in ('A app', 'B shortlist', 'C catalog', 'D hybrid')}
    examples = []

    for seed in seeds:
        if not seed['deezer_id']:
            print(f"Skipping {seed['title']}: not found on Deezer")
            continue
        vectors, seed_seconds = store.embed_many([seed['deezer_id']])
        seed_vec = center(vectors[seed['deezer_id']])
        pool_vectors, pool_seconds = store.embed_many([p['deezer_id'] for p in seed['pool']])

        # B: rerank the app's shortlist with EffNet instead of librosa
        pool = [p for p in seed['pool'] if p['deezer_id'] in pool_vectors]
        pool_audio = rescale([float(center(pool_vectors[p['deezer_id']]) @ seed_vec) for p in pool])
        pool_context = rescale([p['context_score'] for p in pool])
        shortlist_recs = pick_diverse(
            [(AUDIO_WEIGHT * a + CONTEXT_WEIGHT * c, p) for a, c, p in zip(pool_audio, pool_context, pool)],
            seed['artist'], seed['title'])

        # C: nearest neighbors in the catalog, no Last.fm involved
        t0 = time.perf_counter()
        catalog_sims = catalog_unit @ seed_vec
        nearest = np.argsort(catalog_sims)[::-1][:CATALOG_NEIGHBORS * 3]
        search_seconds = time.perf_counter() - t0
        neighbors = [dict(catalog[i], context_score=0.0) for i in nearest
                     if normalize_artist(catalog[i]['artist']) != normalize_artist(seed['artist'])][:CATALOG_NEIGHBORS]
        catalog_recs = pick_diverse([(float(catalog_sims[i]), catalog[i]) for i in nearest
                                     if normalize_artist(catalog[i]['artist']) != normalize_artist(seed['artist'])],
                                    seed['artist'], seed['title'])

        # D: shortlist plus catalog neighbors; catalog songs earn context if Last.fm relates their artist
        related_artists = similar_artists(seed['artist'])
        union = pool + neighbors
        union_audio = rescale(
            [float(center(pool_vectors[p['deezer_id']]) @ seed_vec) for p in pool]
            + [float(catalog_sims[i]) for i in nearest
               if normalize_artist(catalog[i]['artist']) != normalize_artist(seed['artist'])][:CATALOG_NEIGHBORS])
        context = []
        for item in union:
            artist = normalize_artist(item['artist'])
            artist_context = 1 - related_artists.index(artist) / len(related_artists) if artist in related_artists else 0
            context.append(max(item['context_score'], 0.5 * artist_context))
        hybrid_recs = pick_diverse(
            [(AUDIO_WEIGHT * a + CONTEXT_WEIGHT * c, item) for a, c, item in zip(union_audio, rescale(context), union)],
            seed['artist'], seed['title'])

        methods = {
            'A app': (seed['app_recs'], seed['app_seconds']),
            'B shortlist': (shortlist_recs, seed['shortlist_seconds'] + seed_seconds + pool_seconds),
            'C catalog': (catalog_recs, seed_seconds + search_seconds),
            'D hybrid': (hybrid_recs, seed['shortlist_seconds'] + seed_seconds + pool_seconds + search_seconds),
        }
        app_vectors, _ = store.embed_many([r['deezer_id'] for r in seed['app_recs']])
        catalog_lookup = {(c['title'], c['artist']): catalog_unit[i] for i, c in enumerate(catalog)}

        def sound(rec):
            if rec.get('deezer_id') in pool_vectors:
                return float(center(pool_vectors[rec['deezer_id']]) @ seed_vec)
            if rec.get('deezer_id') in app_vectors:
                return float(center(app_vectors[rec['deezer_id']]) @ seed_vec)
            vector = catalog_lookup.get((rec['title'], rec['artist']))
            return float(vector @ seed_vec) if vector is not None else np.nan

        for name, (recs, seconds) in methods.items():
            totals[name]['genre'] += [genre_match(r['artist'], seed['genre']) for r in recs]
            totals[name]['related'] += [normalize_artist(r['artist']) in related_artists for r in recs]
            totals[name]['sound'] += [sound(r) for r in recs]
            totals[name]['seconds'].append(seconds)
        examples.append((seed, {name: recs for name, (recs, _) in methods.items()}))
        print(f"  scored {seed['title']} by {seed['artist']}", flush=True)

    save_lastfm_caches()

    print(f"\n{'method':14s} {'genre':>6s} {'related':>8s} {'sound':>6s} {'seconds (median)':>17s}")
    for name, t in totals.items():
        print(f"{name:14s} {np.mean(t['genre']):6.2f} {np.mean(t['related']):8.2f} "
              f"{np.nanmean(t['sound']):6.2f} {np.median(t['seconds']):17.1f}")

    print("\nRecommendations side by side:")
    for seed, recs in examples:
        print(f"\n{seed['title']} by {seed['artist']} ({seed['genre']})")
        for name, items in recs.items():
            listed = '; '.join(f"{r['title']} - {r['artist']}" for r in items)
            print(f"  {name:12s} {listed}")


if __name__ == '__main__':
    main()
