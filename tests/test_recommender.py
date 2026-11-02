import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from cadence import AudioFeatures, EnhancedAudioProcessor, key_similarity, tempo_similarity, _estimate_key, MAJOR_PROFILE  # noqa: E402
from crud import (  # noqa: E402
    MusicRecommender, Track, artists_match, genre_matches, is_alternate_version,
    normalize_title, parse_timeframe,
)


def make_features(seed: int, **overrides) -> AudioFeatures:
    rng = np.random.default_rng(seed)
    values = dict(
        mfcc_mean=rng.normal(0, 20, 13), mfcc_std=rng.uniform(5, 30, 13),
        spectral_contrast=rng.uniform(10, 40, 7), chroma=rng.uniform(0, 1, 12),
        spectral_centroid=rng.uniform(1000, 4000), spectral_bandwidth=rng.uniform(1500, 3500),
        spectral_rolloff=rng.uniform(3000, 8000), spectral_flatness=rng.uniform(0.001, 0.1),
        zero_crossing_rate=rng.uniform(0.02, 0.15), tempo=rng.uniform(70, 170),
        onset_strength=rng.uniform(0.5, 3), onset_density=rng.uniform(1, 6),
        rms_energy=rng.uniform(0.05, 0.4), dynamic_range=rng.uniform(5, 30),
        key_signature=int(rng.integers(0, 12)), mode=int(rng.integers(0, 2)),
    )
    values.update(overrides)
    return AudioFeatures(**values)


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
        assert [(t.title, t.context_score) for t in kept] == [("Alive (2004 Remaster)", 0.6), ("Demons", 0.5)]

    def test_diversify_caps_tracks_per_artist(self):
        tracks = [Track(i, f"Song {i}", "Same Artist") for i in range(4)] + [Track(9, "Other", "Other Artist")]
        picked = MusicRecommender._diversify(tracks, limit=3, max_per_artist=1)
        assert [t.artist_name for t in picked] == ["Same Artist", "Other Artist"]


class TestAudioSimilarity:
    def test_tempo_similarity_handles_double_time(self):
        assert tempo_similarity(120, 120) == pytest.approx(1.0)
        assert tempo_similarity(120, 240) > tempo_similarity(120, 150)
        assert tempo_similarity(120, 125) > tempo_similarity(120, 140)

    def test_key_similarity_on_circle_of_fifths(self):
        C, G, Fs, A = 0, 7, 6, 9
        assert key_similarity(C, 1, C, 1) == 1.0
        assert key_similarity(C, 1, A, 0) == 1.0   # relative minor
        assert key_similarity(C, 1, G, 1) > key_similarity(C, 1, Fs, 1)
        assert key_similarity(C, 1, Fs, 1) == 0.0  # tritone, furthest away

    def test_key_estimation_on_ideal_profiles(self):
        for tonic in range(12):
            assert _estimate_key(np.roll(MAJOR_PROFILE, tonic)) == (tonic, 1)

    def test_closer_tracks_score_higher_and_scores_spread_out(self):
        reference = make_features(0)
        near = make_features(0, tempo=reference.tempo * 1.02,
                             mfcc_mean=reference.mfcc_mean + 1.0, spectral_centroid=reference.spectral_centroid * 1.05)
        others = [make_features(seed) for seed in range(1, 15)]
        scores = EnhancedAudioProcessor().calculate_advanced_similarity(reference, [near] + others)

        assert scores[0] == max(scores)
        assert all(0.0 <= s <= 1.0 for s in scores)
        # The old raw-cosine approach put nearly everything between ~0.8 and ~0.9
        assert max(scores) - min(scores) > 0.3


def test_display_title_hides_remaster_tags():
    from crud import display_title
    assert display_title("The Chain - 2004 Remaster") == "The Chain"
    assert display_title("Come Together (Remastered 2009)") == "Come Together"
    assert display_title("Stay (feat. Someone)") == "Stay (feat. Someone)"
