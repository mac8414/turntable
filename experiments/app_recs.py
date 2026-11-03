"""
Step 5b: run the app's real recommender (Last.fm shortlist + librosa) for each seed song, cold,
and save its recommendations, timing, and the shortlist it analyzed, so catalog_eval.py can
rerank the exact same candidates with Discogs-EffNet.

Uses the app's environment. Run from the project root:  python experiments/app_recs.py
Written against the v2 recommender (librosa); run it from the v2 branch to reproduce step 5.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import crud  # noqa: E402
from crud import MusicRecommender  # noqa: E402
from evaluation import CACHE_DIR  # noqa: E402

SEEDS = [
    ('rock', 'Whole Lotta Love', 'Led Zeppelin'),
    ('metal', 'Enter Sandman', 'Metallica'),
    ('hip-hop', 'N.Y. State of Mind', 'Nas'),
    ('electronic', 'Strobe', 'deadmau5'),
    ('jazz', 'So What', 'Miles Davis'),
    ('classical', 'Clair de Lune', 'Claude Debussy'),
    ('country', 'Jolene', 'Dolly Parton'),
    ('r&b/soul', "What's Going On", 'Marvin Gaye'),
    ('reggae', 'Could You Be Loved', 'Bob Marley & The Wailers'),
    ('folk', 'Skinny Love', 'Bon Iver'),
]
OUTPUT_PATH = os.path.join(CACHE_DIR, 'app_recs.json')


def track_dict(track):
    return {'title': track.title, 'artist': track.artist_name, 'deezer_id': track.id,
            'context_score': track.context_score, 'score': track.similarity_score}


def shortlist(recommender, title, artist):
    """The same steps get_recommendations takes before audio analysis (no filters)."""
    reference = recommender._resolve_reference(title, artist, None)
    if reference:
        title, artist = reference.title, reference.artist_name
    candidates = recommender._filter_tracks(
        recommender._gather_candidates(title, artist, crud.SIMILAR_ARTISTS_LIMIT), title, artist)
    candidates.sort(key=lambda t: t.context_score, reverse=True)
    pool = recommender._diversify(candidates, crud.MIN_ANALYSIS_POOL, crud.MAX_POOL_TRACKS_PER_ARTIST)
    return reference, recommender._resolve_on_deezer(pool)


def main():
    results = []
    for genre, title, artist in SEEDS:
        # A fresh recommender per seed so nothing is cached between seeds
        t0 = time.perf_counter()
        result = MusicRecommender().get_recommendations(title, artist, 5)
        app_seconds = time.perf_counter() - t0

        # Time just the Last.fm + Deezer part (cold), which methods B and D also need
        t0 = time.perf_counter()
        reference, pool = shortlist(MusicRecommender(), title, artist)
        shortlist_seconds = time.perf_counter() - t0

        results.append({
            'genre': genre, 'title': title, 'artist': artist,
            'deezer_id': reference.id if reference else None,
            'app_seconds': app_seconds, 'shortlist_seconds': shortlist_seconds,
            'app_recs': [track_dict(t) for t in result.tracks],
            'pool': [track_dict(t) for t in pool],
        })
        print(f"{title} by {artist}: app {app_seconds:.1f}s, shortlist {shortlist_seconds:.1f}s, "
              f"{len(pool)} candidates", flush=True)

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(results, f, indent=1)


if __name__ == '__main__':
    main()
