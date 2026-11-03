import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from crud import (  # noqa: E402
    MusicRecommender, Track, artists_match, display_title, genre_matches, is_alternate_version,
    normalize_title, parse_timeframe, song_key, split_artists,
)
from embeddings import EMBEDDING_SIZE, SongCatalog  # noqa: E402


class TestTitleHandling:
    @pytest.mark.parametrize("title", ["Demons", "Alive", "Live Forever", "Credit", "Discover", "Olive Tree"])
    def test_real_titles_are_not_treated_as_alternate_versions(self, title):
        assert not is_alternate_version(title)

    @pytest.mark.parametrize("title", ["Black (Live)", "Song - Live at Wembley", "Track [Remix]",
                                       "Hey - Acoustic Version", "Tune (Sped Up)"])
    def test_alternate_versions_are_detected(self, title):
        assert is_alternate_version(title)

    def test_normalize_title_strips_versions_and_features(self):
        assert normalize_title("Black (2009 Remaster)") == "black"
        assert normalize_title("Come Together - Remastered 2019") == "come together"
        assert normalize_title("Señorita feat. Someone") == "senorita"

    def test_artists_match(self):
        assert artists_match("The Beatles", "Beatles")
        assert artists_match("Bob Marley & The Wailers", "Bob Marley")
        assert artists_match("Beyoncé", "Beyonce")
        assert not artists_match("U2", "U2 Tribute Band")  # short names only match exactly
        assert not artists_match("Pearl Jam", "Pearl")
        assert not artists_match("Drake", "Nick Drake")

    def test_split_artists_handles_collaborations(self):
        assert split_artists("Porter Wagoner & Dolly Parton") >= {"porter wagoner", "dolly parton"}
        assert split_artists("deadmau5 & Kaskade") & split_artists("Kaskade & deadmau5")
        assert split_artists("Drake feat. Rihanna") >= {"drake", "rihanna"}
        assert not split_artists("Drake") & split_artists("Nick Drake")

    def test_song_key_ignores_versions_and_featured_artists(self):
        assert song_key("Black (2009 Remaster)", "Pearl Jam") == song_key("Black", "Pearl Jam")
        assert song_key("Work", "Rihanna feat. Drake") == song_key("Work", "Rihanna")

    def test_display_title_hides_remaster_tags(self):
        assert display_title("The Chain - 2004 Remaster") == "The Chain"
        assert display_title("Come Together (Remastered 2009)") == "Come Together"
        assert display_title("Stay (feat. Someone)") == "Stay (feat. Someone)"


class TestFilters:
    def test_parse_timeframe(self):
        assert parse_timeframe("60s") == (1960, 1969)
        assert parse_timeframe("90s") == (1990, 1999)
        assert parse_timeframe("2000s") == (2000, 2009)
        assert parse_timeframe("2020s") == (2020, 2029)
        assert parse_timeframe("Any") is None
        assert parse_timeframe(None) is None

    def test_genre_matches(self):
        assert genre_matches(["alternative rock", "grunge"], "Rock")
        assert genre_matches(["hip hop", "west coast"], "Hip-Hop")
        assert not genre_matches(["country", "americana"], "Metal")

    def test_filter_tracks_dedupes_and_drops_reference(self):
        recommender = MusicRecommender.__new__(MusicRecommender)
        tracks = [
            Track(0, "Black", "Pearl Jam", context_score=1.0),               # the reference itself
            Track(0, "Alive", "Pearl Jam", context_score=0.3),
            Track(0, "Alive (2004 Remaster)", "Pearl Jam", context_score=0.6),  # duplicate, higher score wins
            Track(0, "Even Flow (Live)", "Pearl Jam", context_score=0.9),     # alternate version
            Track(0, "Demons", "Imagine Dragons", context_score=0.5),
        ]
        kept = recommender._filter_tracks(tracks, "Black", "Pearl Jam")
        assert sorted((t.title, t.context_score) for t in kept) == [("Alive (2004 Remaster)", 0.6), ("Demons", 0.5)]

    def test_filter_tracks_dedupes_collaboration_credits(self):
        recommender = MusicRecommender.__new__(MusicRecommender)
        tracks = [
            Track(0, "I Remember", "deadmau5 & Kaskade", context_score=0.5),
            Track(0, "I Remember", "Kaskade & deadmau5", context_score=0.4),
            Track(0, "The Last Thing on My Mind", "Porter Wagoner & Dolly Parton", context_score=0.3),
            Track(0, "The Last Thing on My Mind", "Porter Wagoner", context_score=0.2),
            Track(0, "Hurt", "Johnny Cash", context_score=0.2),
            Track(0, "Hurt", "Nine Inch Nails", context_score=0.1),  # same title, different artist: keep
        ]
        kept = recommender._filter_tracks(tracks, "Seed", "Someone")
        assert sorted((t.title, t.artist_name) for t in kept) == [
            ("Hurt", "Johnny Cash"), ("Hurt", "Nine Inch Nails"), ("I Remember", "deadmau5 & Kaskade"),
            ("The Last Thing on My Mind", "Porter Wagoner & Dolly Parton"),
        ]

    def test_filter_tracks_drops_seed_under_a_longer_title(self):
        recommender = MusicRecommender.__new__(MusicRecommender)
        tracks = [
            Track(0, "Suite Bergamasque, L. 75: III. Clair de lune", "Claude Debussy", context_score=0.9),
            Track(0, "Arabesque No. 1", "Claude Debussy", context_score=0.5),
            Track(0, "Clair de Lune Dreams", "Someone Else", context_score=0.4),  # other artist: keep
        ]
        kept = recommender._filter_tracks(tracks, "Clair de Lune", "Claude Debussy")
        assert sorted(t.title for t in kept) == ["Arabesque No. 1", "Clair de Lune Dreams"]

    def test_diversify_caps_tracks_per_artist_including_collaborations(self):
        tracks = [
            Track(1, "Song 1", "Same Artist"), Track(2, "Song 2", "Same Artist"),
            Track(3, "Duet", "Same Artist & Guest"), Track(4, "Other", "Other Artist"),
        ]
        picked = MusicRecommender._diversify(tracks, limit=3, max_per_artist=1)
        assert [t.title for t in picked] == ["Song 1", "Other"]


def random_vector(rng, near=None, noise=1.0):
    base = near if near is not None else np.zeros(EMBEDDING_SIZE)
    return (base + rng.normal(0, noise, EMBEDDING_SIZE)).astype(np.float32)


class TestSongCatalog:
    def test_add_find_nearest_and_reload(self, tmp_path):
        rng = np.random.default_rng(0)
        catalog = SongCatalog(str(tmp_path), key_fn=song_key)
        target = random_vector(rng)
        catalog.add({'deezer_id': 1, 'title': 'Twin (Remastered)', 'artist': 'A'}, random_vector(rng, target, 0.1))
        for i in range(2, 12):
            catalog.add({'deezer_id': i, 'title': f'Song {i}', 'artist': f'Artist {i}'}, random_vector(rng))

        assert catalog.find('Twin', 'A')[0]['deezer_id'] == 1
        assert catalog.get(5)[0]['title'] == 'Song 5'
        assert catalog.nearest(target, 1)[0][1]['deezer_id'] == 1
        assert catalog.nearest(target, 1, skip=lambda s: s['deezer_id'] == 1)[0][1]['deezer_id'] != 1

        catalog.update(1, release_year=1994)
        catalog.save()
        reloaded = SongCatalog(str(tmp_path), key_fn=song_key)
        assert len(reloaded) == 11
        assert reloaded.get(1)[0]['release_year'] == 1994
        np.testing.assert_allclose(reloaded.get(1)[1], catalog.get(1)[1])


class FakeEmbedder:
    """Returns preset embeddings by preview URL instead of running the model."""
    def __init__(self, by_url):
        self.by_url = by_url

    def embed_urls(self, urls):
        return [self.by_url.get(url) for url in urls]


def test_hybrid_recommendations_blend_listeners_and_catalog(tmp_path):
    rng = np.random.default_rng(1)
    seed_vec = random_vector(rng)

    catalog = SongCatalog(str(tmp_path), key_fn=song_key)
    catalog_songs = [
        ('Sound Twin', 'Unknown Artist', random_vector(rng, seed_vec, 0.2)),        # sounds alike, unrelated
        ('Friend Song', 'Catalog Friend', random_vector(rng, seed_vec, 0.5)),       # sounds alike, related artist
        ('Other Seed Song', 'Seed Artist', random_vector(rng, seed_vec, 0.1)),      # seed artist: never from catalog
    ] + [(f'Filler {i}', f'Filler Artist {i}', random_vector(rng)) for i in range(20)]
    for i, (title, artist, vector) in enumerate(catalog_songs, start=100):
        catalog.add({'deezer_id': i, 'title': title, 'artist': artist, 'cover': None}, vector)

    embedder = FakeEmbedder({
        'seed.mp3': seed_vec,
        'close.mp3': random_vector(rng, seed_vec, 0.3),
        'far.mp3': random_vector(rng),
    })
    recommender = MusicRecommender(embedder=embedder, catalog=catalog)
    deezer_tracks = {
        'Close Song': Track(2, 'Close Song', 'Related A', preview_url='close.mp3'),
        'Far Song': Track(3, 'Far Song', 'Related B', preview_url='far.mp3'),
    }
    recommender._resolve_reference = lambda *args: Track(1, 'Seed Song', 'Seed Artist', preview_url='seed.mp3')
    recommender.deezer_client.find_track = lambda title, artist: deezer_tracks.get(title)
    lastfm = recommender.lastfm_client
    lastfm.get_similar_tracks = lambda artist, track: [
        Track(0, 'Close Song', 'Related A', context_score=1.0),
        Track(0, 'Far Song', 'Related B', context_score=0.9),
    ]
    lastfm.get_similar_artists = lambda artist, limit: [('Related A', 1.0), ('Related B', 0.9), ('Catalog Friend', 0.5)]
    lastfm.get_artist_top_tracks = lambda artist, limit: []

    result = recommender.get_recommendations('Seed Song', 'Seed Artist', 4, track_id=1)
    titles = [t.title for t in result.tracks]
    sources = {t.title: t.source for t in result.tracks}

    assert 'Other Seed Song' not in titles                      # catalog never suggests the seed artist
    assert {'Close Song', 'Sound Twin', 'Friend Song'} <= set(titles)
    if 'Far Song' in titles:  # related but sounds different: may be included, but below the close match
        assert titles.index('Close Song') < titles.index('Far Song')
    assert sources['Close Song'] == 'related' and sources['Sound Twin'] == 'sound'
    assert all(0 <= t.similarity_score <= 1 for t in result.tracks)
    # Everything analyzed during the request is saved for next time
    assert catalog.get(1) and catalog.get(2) and catalog.get(3)
    assert SongCatalog(str(tmp_path), key_fn=song_key).get(2) is not None
