import os
import tempfile
import logging
import subprocess
import warnings
from dataclasses import dataclass
from typing import List, Optional

import librosa
import numpy as np
import requests

# Suppress librosa warnings for cleaner output
warnings.filterwarnings('ignore', category=UserWarning, module='librosa')
warnings.filterwarnings('ignore', category=FutureWarning, module='librosa')

logger = logging.getLogger(__name__)

SAMPLE_RATE = 22050
MAX_DURATION = 30.0  # Deezer previews are 30 seconds long
HOP_LENGTH = 512
N_FFT = 2048

# Krumhansl-Kessler key profiles, index 0 is the tonic
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# How much each group of features contributes to the overall audio similarity
SIMILARITY_WEIGHTS = {
    'timbre': 0.30,    # MFCCs: what instruments/voices sound like
    'texture': 0.20,   # Spectral shape: brightness, noisiness
    'rhythm': 0.15,    # Tempo
    'energy': 0.15,    # Loudness, dynamics, onset density
    'harmony': 0.10,   # Pitch-class content
    'key': 0.10,       # Key compatibility on the circle of fifths
}


@dataclass
class AudioFeatures:
    """Summary statistics of a track's audio. Small enough to cache."""
    mfcc_mean: np.ndarray          # 13
    mfcc_std: np.ndarray           # 13
    spectral_contrast: np.ndarray  # 7
    chroma: np.ndarray             # 12
    spectral_centroid: float
    spectral_bandwidth: float
    spectral_rolloff: float
    spectral_flatness: float
    zero_crossing_rate: float
    tempo: float
    onset_strength: float
    onset_density: float           # onsets per second
    rms_energy: float
    dynamic_range: float           # dB between loud (95th pct) and quiet (5th pct) frames
    key_signature: int             # 0-11 for C, C#, D, ...
    mode: int                      # 0 for minor, 1 for major

    def timbre_vector(self) -> np.ndarray:
        # MFCC 0 is overall loudness, which the energy group already covers
        return np.concatenate([self.mfcc_mean[1:], self.mfcc_std[1:]])

    def texture_vector(self) -> np.ndarray:
        # Log-scale the frequency features so they are compared by ratio, not by Hz
        return np.concatenate([
            np.log([
                max(self.spectral_centroid, 1.0),
                max(self.spectral_bandwidth, 1.0),
                max(self.spectral_rolloff, 1.0),
                max(self.spectral_flatness, 1e-10),
            ]),
            [self.zero_crossing_rate],
            self.spectral_contrast,
        ])

    def energy_vector(self) -> np.ndarray:
        return np.array([self.rms_energy, self.dynamic_range, self.onset_strength, self.onset_density])

    def to_vector(self) -> np.ndarray:
        """Convert all features to a single feature vector"""
        return np.concatenate([
            self.timbre_vector(),
            self.texture_vector(),
            self.energy_vector(),
            self.chroma,
            [self.tempo, self.key_signature / 12.0, self.mode],
        ]).astype(np.float32)


def _estimate_tempo(onset_envelope: np.ndarray, sr: int) -> float:
    # librosa.beat.tempo moved to librosa.feature.rhythm.tempo in 0.10 and was removed in 0.11
    rhythm = getattr(librosa.feature, 'rhythm', None)
    tempo_fn = rhythm.tempo if rhythm is not None else librosa.beat.tempo
    return float(np.atleast_1d(tempo_fn(onset_envelope=onset_envelope, sr=sr, hop_length=HOP_LENGTH))[0])


def _estimate_key(chroma_mean: np.ndarray) -> tuple:
    """Krumhansl-Schmuckler key finding. Returns (tonic 0-11, mode 1=major/0=minor)."""
    if np.allclose(chroma_mean, chroma_mean[0]):
        return 0, 1
    best = (0, 1, -np.inf)
    for tonic in range(12):
        for mode, profile in ((1, MAJOR_PROFILE), (0, MINOR_PROFILE)):
            corr = np.corrcoef(chroma_mean, np.roll(profile, tonic))[0, 1]
            if np.isfinite(corr) and corr > best[2]:
                best = (tonic, mode, corr)
    return best[0], best[1]


def tempo_similarity(t1: float, t2: float) -> float:
    """Compare tempos by ratio, treating half/double-time as close (a common estimation error)."""
    if not t1 or not t2 or t1 <= 0 or t2 <= 0:
        return 0.5
    octaves = abs(np.log2(t1 / t2))
    folded = octaves % 1.0
    folded = min(folded, 1.0 - folded)
    octave_penalty = 0.9 ** round(octaves)
    return float(np.exp(-folded / 0.15) * octave_penalty)


def key_similarity(key1: int, mode1: int, key2: int, mode2: int) -> float:
    """1.0 for the same/relative key, falling off with distance on the circle of fifths."""
    # Map minor keys to their relative major so A minor == C major
    rel1 = key1 if mode1 else (key1 + 3) % 12
    rel2 = key2 if mode2 else (key2 + 3) % 12
    distance = abs((rel1 * 7) % 12 - (rel2 * 7) % 12)
    distance = min(distance, 12 - distance)
    return 1.0 - distance / 6.0


def _pool_similarity(reference: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """
    Similarity of each candidate row to the reference after scaling every feature by its
    spread across the whole pool, so features measured in Hz don't drown out ones measured in 0-1.
    """
    pool = np.vstack([reference, candidates])
    q75, q25 = np.percentile(pool, [75, 25], axis=0)
    scale = (q75 - q25) / 1.349  # IQR -> standard deviation for normal data
    std = pool.std(axis=0)
    scale = np.where(scale > 1e-9, scale, std)
    scale = np.where(scale > 1e-9, scale, 1.0)
    z_diff = (candidates - reference) / scale
    rms_diff = np.sqrt(np.mean(z_diff ** 2, axis=1))
    # Two unrelated tracks average ~1.4 standard deviations apart, which maps to ~0.4
    return np.exp(-rms_diff / 1.5)


class EnhancedAudioProcessor:

    @staticmethod
    def download_audio(url: str, filename: Optional[str] = None) -> Optional[str]:
        """Downloads audio from a URL to a local file"""
        if not filename:
            temp_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            filename = temp_file.name
            temp_file.close()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.deezer.com",
            "Accept": "audio/mpeg, audio/*, */*",
        }

        try:
            response = requests.get(url, headers=headers, stream=True, timeout=15)
            if response.status_code not in (200, 206):
                logger.error(f"HTTP error downloading audio: {response.status_code}")
                os.remove(filename)
                return None

            total_size = 0
            with open(filename, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)
                        total_size += len(chunk)
                        # Stop if file gets too large (> 5MB)
                        if total_size > 5 * 1024 * 1024:
                            logger.warning(f"File too large, stopping download: {filename}")
                            break

            file_size = os.path.getsize(filename)
            if file_size < 10 * 1024:  # Less than 10KB
                logger.error(f"Downloaded file too small: {filename} ({file_size} bytes)")
                os.remove(filename)
                return None

            return filename

        except Exception as e:
            logger.error(f"Exception downloading audio: {e}")
            if filename and os.path.exists(filename):
                os.remove(filename)
            return None

    @staticmethod
    def convert_mp3_to_wav(mp3_path: str) -> Optional[str]:
        """Convert with ffmpeg as a fallback when librosa can't decode the MP3 directly"""
        wav_path = mp3_path.rsplit('.', 1)[0] + '.wav'
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-i', mp3_path, '-acodec', 'pcm_s16le', '-ar', str(SAMPLE_RATE), wav_path],
                check=True,
                capture_output=True,
                timeout=30
            )
            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
                return wav_path
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"ffmpeg conversion failed: {e}")
        if os.path.exists(wav_path):
            os.remove(wav_path)
        return None

    def _load_audio(self, audio_path: str):
        try:
            return librosa.load(audio_path, sr=SAMPLE_RATE, mono=True, duration=MAX_DURATION)
        except Exception as e:
            logger.warning(f"Failed to load audio directly, trying ffmpeg: {e}")

        wav_path = self.convert_mp3_to_wav(audio_path)
        if not wav_path:
            return None, None
        try:
            return librosa.load(wav_path, sr=SAMPLE_RATE, mono=True, duration=MAX_DURATION)
        except Exception as e:
            logger.error(f"Failed to load converted audio: {e}")
            return None, None
        finally:
            os.remove(wav_path)

    def extract_comprehensive_features(self, audio_path: str) -> Optional[AudioFeatures]:
        """Extract summary audio features from a file"""
        try:
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 10 * 1024:
                logger.error(f"Audio file missing or too small: {audio_path}")
                return None

            y, sr = self._load_audio(audio_path)
            if y is None or len(y) == 0 or np.max(np.abs(y)) < 1e-4:
                logger.error(f"Empty or silent audio loaded from: {audio_path}")
                return None

            # Normalize peak level so tracks mastered at different volumes compare fairly
            y = librosa.util.normalize(y)

            # Ensure minimum audio length (at least 1 second)
            if len(y) < sr:
                y = np.pad(y, (0, sr - len(y)), mode='constant')

            # Precompute spectrogram to share across features
            stft = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH))

            # Timbre
            mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=HOP_LENGTH)

            # Spectral texture
            spectral_centroid = np.mean(librosa.feature.spectral_centroid(S=stft, sr=sr))
            spectral_bandwidth = np.mean(librosa.feature.spectral_bandwidth(S=stft, sr=sr))
            spectral_contrast = librosa.feature.spectral_contrast(S=stft, sr=sr, n_bands=6)
            spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(S=stft, sr=sr))
            spectral_flatness = np.mean(librosa.feature.spectral_flatness(S=stft))
            zcr = np.mean(librosa.feature.zero_crossing_rate(y, hop_length=HOP_LENGTH))

            # Harmony and key
            chroma_mean = np.mean(librosa.feature.chroma_stft(S=stft ** 2, sr=sr), axis=1)
            key_signature, mode = _estimate_key(chroma_mean)

            # Rhythm
            onset_envelope = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP_LENGTH)
            tempo = _estimate_tempo(onset_envelope, sr)
            onsets = librosa.onset.onset_detect(onset_envelope=onset_envelope, sr=sr, hop_length=HOP_LENGTH)
            onset_density = len(onsets) / (len(y) / sr)

            # Dynamics
            rms = librosa.feature.rms(S=stft, frame_length=N_FFT, hop_length=HOP_LENGTH)[0]
            loud, quiet = np.percentile(rms, [95, 5])
            dynamic_range = 20 * np.log10((loud + 1e-6) / (quiet + 1e-6))

            features = AudioFeatures(
                mfcc_mean=np.mean(mfccs, axis=1),
                mfcc_std=np.std(mfccs, axis=1),
                spectral_contrast=np.mean(spectral_contrast, axis=1),
                chroma=chroma_mean,
                spectral_centroid=float(spectral_centroid),
                spectral_bandwidth=float(spectral_bandwidth),
                spectral_rolloff=float(spectral_rolloff),
                spectral_flatness=float(spectral_flatness),
                zero_crossing_rate=float(zcr),
                tempo=tempo,
                onset_strength=float(np.mean(onset_envelope)),
                onset_density=float(onset_density),
                rms_energy=float(np.mean(rms)),
                dynamic_range=float(dynamic_range),
                key_signature=int(key_signature),
                mode=int(mode),
            )

            if not np.isfinite(features.to_vector()).all():
                logger.warning(f"Feature vector contains invalid values: {audio_path}")
                return None

            return features

        except Exception as e:
            logger.error(f"Unexpected error in feature extraction: {e}")
            return None

    def calculate_advanced_similarity(self, reference_features: AudioFeatures,
                                      comparison_features: List[AudioFeatures]) -> List[float]:
        """
        Similarity (0-1) of each comparison track to the reference. Vector features are scaled
        across the pool of tracks being compared, so scores are relative to that pool.
        """
        if not comparison_features:
            return []

        group_scores = {}
        for group, vector_fn in (
            ('timbre', AudioFeatures.timbre_vector),
            ('texture', AudioFeatures.texture_vector),
            ('energy', AudioFeatures.energy_vector),
            ('harmony', lambda f: f.chroma),
        ):
            reference = vector_fn(reference_features)
            candidates = np.array([vector_fn(f) for f in comparison_features])
            group_scores[group] = _pool_similarity(reference, candidates)

        group_scores['rhythm'] = np.array([
            tempo_similarity(reference_features.tempo, f.tempo) for f in comparison_features
        ])
        group_scores['key'] = np.array([
            key_similarity(reference_features.key_signature, reference_features.mode,
                           f.key_signature, f.mode)
            for f in comparison_features
        ])

        total = sum(SIMILARITY_WEIGHTS[group] * scores for group, scores in group_scores.items())
        return [float(np.clip(score, 0.0, 1.0)) for score in total]
