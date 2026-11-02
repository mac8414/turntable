"""
How well do CadenceAI's audio features capture how a song sounds?

For a labeled set of tracks, rank every other track by audio similarity (ignoring tracks by the
same artist, so we don't just measure "same band") and check how often the nearest neighbors share
the query's genre. Random guessing scores about 0.08.

Run from the project root:  python experiments/genre_eval.py
Downloaded previews are kept in experiments/.cache so other feature extractors can reuse them.
"""
import json
import os
import pickle
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import cadence  # noqa: E402
from cadence import EnhancedAudioProcessor  # noqa: E402
from crud import DeezerClient, artists_match  # noqa: E402
from evaluation import (  # noqa: E402
    AUDIO_DIR, CACHE_DIR, TRACKS_PATH, evaluate, print_genre_breakdown, print_header, print_row, random_baseline,
)

DATASET = {
    'rock': {
        'Led Zeppelin': ['Whole Lotta Love', 'Black Dog', 'Immigrant Song'],
        'Foo Fighters': ['Everlong', 'The Pretender', 'Best of You'],
        'The Rolling Stones': ['Paint It Black', 'Gimme Shelter', 'Start Me Up'],
    },
    'metal': {
        'Metallica': ['Master of Puppets', 'Enter Sandman', 'Battery'],
        'Slayer': ['Raining Blood', 'Angel of Death', 'South of Heaven'],
        'Iron Maiden': ['The Trooper', 'Run to the Hills', 'Aces High'],
    },
    'hip-hop': {
        'Kendrick Lamar': ['HUMBLE.', 'DNA.', 'Alright'],
        'Nas': ['N.Y. State of Mind', 'The World Is Yours', 'If I Ruled the World'],
        'Wu-Tang Clan': ['C.R.E.A.M.', 'Protect Ya Neck', 'Triumph'],
    },
    'electronic': {
        'Daft Punk': ['Around the World', 'Da Funk', 'One More Time'],
        'deadmau5': ['Strobe', "Ghosts 'n' Stuff", 'I Remember'],
        'Disclosure': ['Latch', 'White Noise', 'You & Me'],
    },
    'jazz': {
        'Miles Davis': ['So What', 'Freddie Freeloader', 'Blue in Green'],
        'John Coltrane': ['Giant Steps', 'My Favorite Things', 'Naima'],
        'The Dave Brubeck Quartet': ['Take Five', 'Blue Rondo à la Turk', 'Strange Meadow Lark'],
    },
    'classical': {
        'Wolfgang Amadeus Mozart': ['Eine kleine Nachtmusik', 'Lacrimosa', 'Symphony No. 40'],
        'Ludwig van Beethoven': ['Moonlight Sonata', 'Symphony No. 5', 'Für Elise'],
        'Antonio Vivaldi': ['Spring', 'Winter', 'Summer'],
    },
    'country': {
        'Johnny Cash': ['Ring of Fire', 'Folsom Prison Blues', 'I Walk the Line'],
        'Dolly Parton': ['Jolene', '9 to 5', 'Coat of Many Colors'],
        'Luke Combs': ['Fast Car', 'Beautiful Crazy', 'When It Rains It Pours'],
    },
    'r&b/soul': {
        'Marvin Gaye': ["What's Going On", "Let's Get It On", 'Sexual Healing'],
        'Aretha Franklin': ['Respect', 'Natural Woman', 'Think'],
        'SZA': ['Kill Bill', 'Good Days', 'The Weekend'],
    },
    'reggae': {
        'Bob Marley & The Wailers': ['Is This Love', 'Could You Be Loved', 'Three Little Birds'],
        'Toots and the Maytals': ['Pressure Drop', '54-46 That\'s My Number', 'Funky Kingston'],
        'Peter Tosh': ['Legalize It', 'Equal Rights', 'Johnny B. Goode'],
    },
    'folk': {
        'Simon & Garfunkel': ['The Sound of Silence', 'Scarborough Fair', 'The Boxer'],
        'Bon Iver': ['Skinny Love', 'Holocene', 'Flume'],
        'Fleet Foxes': ['White Winter Hymnal', 'Mykonos', 'Helplessness Blues'],
    },
}


def find_preview(deezer_client, title, artist):
    """First Deezer result by this artist that has a preview (looser than the app's exact-title match)."""
    for result in deezer_client.search(f"{artist} {title}", limit=10):
        if result.preview and artists_match(result.artist.name, artist):
            return result
    return None


def build_dataset():
    """Download previews and extract features, caching both. Returns a list of track dicts."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    features_path = os.path.join(CACHE_DIR, 'cadence_features.pkl')
    cached = pickle.load(open(features_path, 'rb')) if os.path.exists(features_path) else {}

    deezer_client = DeezerClient()
    processor = EnhancedAudioProcessor()
    tracks = []
    for genre, artists in DATASET.items():
        for artist, titles in artists.items():
            for title in titles:
                key = (artist, title)
                if key not in cached:
                    result = find_preview(deezer_client, title, artist)
                    if not result:
                        print(f"  MISSING on Deezer: {title} by {artist}")
                        continue
                    path = os.path.join(AUDIO_DIR, f"{result.id}.mp3")
                    if not os.path.exists(path):
                        processor.download_audio(result.preview, path)
                    features = processor.extract_comprehensive_features(path) if os.path.exists(path) else None
                    if features is None:
                        print(f"  FAILED analysis: {title} by {artist}")
                        continue
                    cached[key] = {'deezer_id': result.id, 'deezer_title': result.title, 'features': features}
                    print(f"  analyzed {title} by {artist} -> {result.title}")
                tracks.append({'genre': genre, 'artist': artist, 'title': title, **cached[key]})

    pickle.dump(cached, open(features_path, 'wb'))
    # Track list for experiments that run in other environments (no librosa)
    with open(TRACKS_PATH, 'w') as f:
        json.dump([{k: t[k] for k in ('genre', 'artist', 'title', 'deezer_id')} for t in tracks], f, indent=1)
    return tracks


def original_similarity(ref, comp):
    """Approximation of the summer version's formula (raw-value cosines, exact key match)."""
    def cos01(a, b):
        a, b = np.asarray(a, float), np.asarray(b, float)
        return (np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12) + 1) / 2
    spectral = lambda f: [f.spectral_centroid, f.spectral_bandwidth, f.spectral_rolloff,
                          f.spectral_flatness, f.zero_crossing_rate]
    return (0.25 * cos01(ref.mfcc_mean, comp.mfcc_mean)
            + 0.15 * cos01(ref.chroma, comp.chroma)
            + 0.2 * np.exp(-abs(ref.tempo - comp.tempo) / 15)
            + 0.2 * cos01(spectral(ref), spectral(comp))
            + 0.1 * cos01([ref.rms_energy, ref.dynamic_range], [comp.rms_energy, comp.dynamic_range])
            + 0.1 * ((ref.key_signature == comp.key_signature) + (ref.mode == comp.mode)) / 2)


def similarity_matrix(tracks, method):
    n = len(tracks)
    features = [t['features'] for t in tracks]
    sims = np.zeros((n, n))
    processor = EnhancedAudioProcessor()
    for i in range(n):
        if method == 'original':
            sims[i] = [original_similarity(features[i], f) for f in features]
        else:
            # The whole dataset acts as the pool, as the candidates do in the app
            sims[i] = processor.calculate_advanced_similarity(features[i], features)
    return sims


def main():
    print("Building dataset...")
    tracks = build_dataset()
    genres = Counter(t['genre'] for t in tracks)
    print(f"\n{len(tracks)} tracks across {len(genres)} genres: {dict(genres)}\n")

    print_header()
    print_row('random guessing', random_baseline(tracks))
    print_row('original (summer) formula', *evaluate(tracks, similarity_matrix(tracks, 'original'))[:2])

    full_weights = dict(cadence.SIMILARITY_WEIGHTS)
    p, nn, per_genre, confusion = evaluate(tracks, similarity_matrix(tracks, 'current'))
    print_row('current formula', p, nn)

    # Each feature group on its own
    for group in full_weights:
        cadence.SIMILARITY_WEIGHTS.clear()
        cadence.SIMILARITY_WEIGHTS.update({g: float(g == group) for g in full_weights})
        print_row('  only ' + group, *evaluate(tracks, similarity_matrix(tracks, 'current'))[:2])
    cadence.SIMILARITY_WEIGHTS.clear()
    cadence.SIMILARITY_WEIGHTS.update(full_weights)

    print_genre_breakdown(tracks, per_genre, confusion)


if __name__ == '__main__':
    main()
