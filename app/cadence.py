import os
import tempfile
import logging
import subprocess
import numpy as np
import librosa
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.decomposition import PCA
import warnings
from sklearn.metrics.pairwise import cosine_similarity
from scipy.stats import pearsonr

# Suppress librosa warnings for cleaner output
warnings.filterwarnings('ignore', category=UserWarning, module='librosa')

logger = logging.getLogger(__name__)

@dataclass
class AudioFeatures:
    """Comprehensive audio features container"""
    # Spectral features
    mfccs: np.ndarray
    spectral_centroid: float
    spectral_bandwidth: float
    spectral_contrast: np.ndarray
    spectral_rolloff: float
    spectral_flatness: float
    zero_crossing_rate: float
    
    # Harmonic features
    chroma: np.ndarray
    tonnetz: np.ndarray
    
    # Rhythmic features
    tempo: float
    beat_strength: float
    onset_strength: float
    
    # Dynamic features
    rms_energy: float
    dynamic_range: float
    
    # High-level features
    key_signature: int  # 0-11 for C, C#, D, etc.
    mode: int  # 0 for minor, 1 for major
    
    def to_vector(self) -> np.ndarray:
        """Convert all features to a single feature vector"""
        features = []
        
        # Add all array features (take mean across time)
        features.extend(np.mean(self.mfccs, axis=1))  # 13 features
        features.extend(np.mean(self.spectral_contrast, axis=1))  # 7 features
        features.extend(np.mean(self.chroma, axis=1))  # 12 features
        features.extend(np.mean(self.tonnetz, axis=1))  # 6 features
        
        # Add scalar features
        scalar_features = [
            self.spectral_centroid,
            self.spectral_bandwidth,
            self.spectral_rolloff,
            self.spectral_flatness,
            self.zero_crossing_rate,
            self.tempo,
            self.beat_strength,
            self.onset_strength,
            self.rms_energy,
            self.dynamic_range,
            self.key_signature / 12.0,  # Normalize to 0-1
            self.mode
        ]
        
        features.extend(scalar_features)
        
        return np.array(features, dtype=np.float32)

class EnhancedAudioProcessor:
    def __init__(self):
        self.scaler = RobustScaler()  # More robust to outliers than StandardScaler
        self.pca = None  # Optional dimensionality reduction
        
    @staticmethod
    def download_audio(url: str, filename: Optional[str] = None) -> Optional[str]:
        """Downloads audio from a URL to a local file with improved error handling"""
        if not filename:
            temp_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            filename = temp_file.name
            temp_file.close()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.deezer.com",
            "Accept": "audio/mpeg, audio/*, */*",
            "Range": "bytes=0-"
        }
        
        try:
            import requests
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            
            if response.status_code in [200, 206]:
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
                
                # Validate file size
                file_size = os.path.getsize(filename)
                if file_size < 10 * 1024:  # Less than 10KB
                    logger.error(f"Downloaded file too small: {filename} ({file_size} bytes)")
                    os.remove(filename)
                    return None
                    
                logger.info(f"Successfully downloaded {file_size} bytes to {filename}")
                return filename
            else:
                logger.error(f"HTTP error downloading audio: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Exception downloading audio: {e}")
            if filename and os.path.exists(filename):
                os.remove(filename)
            return None

    @staticmethod
    def convert_mp3_to_wav(mp3_path: str) -> Optional[str]:
        """Enhanced MP3 to WAV conversion with multiple fallback methods"""
        wav_path = mp3_path.replace('.mp3', '.wav')
        
        # Try ffmpeg first
        try:
            result = subprocess.run(
                ['ffmpeg', '-y', '-i', mp3_path, '-acodec', 'pcm_s16le', '-ar', '22050', wav_path],
                check=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
                logger.info(f"Successfully converted to WAV: {wav_path}")
                return wav_path
                
        except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning(f"ffmpeg conversion failed: {e}")
        
        # Fallback: try to use librosa for conversion
        try:
            y, sr = librosa.load(mp3_path, sr=22050)
            import soundfile as sf
            sf.write(wav_path, y, sr)
            
            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
                logger.info(f"Successfully converted using librosa/soundfile: {wav_path}")
                return wav_path
                
        except Exception as e:
            logger.warning(f"Librosa conversion failed: {e}")
        
        # If conversion fails, return original file and let librosa handle it
        logger.info(f"Using original MP3 file: {mp3_path}")
        return mp3_path

    def extract_comprehensive_features(self, audio_path: str) -> Optional[AudioFeatures]:
        """Extract comprehensive audio features using advanced techniques"""
        try:
            # Validate file
            if not os.path.exists(audio_path):
                logger.error(f"Audio file does not exist: {audio_path}")
                return None
                
            file_size = os.path.getsize(audio_path)
            if file_size < 10 * 1024:  # 10KB threshold
                logger.error(f"Audio file too small: {audio_path} ({file_size} bytes)")
                return None

            # Load audio with optimal parameters
            try:
                # Load with specific parameters for better feature extraction
                y, sr = librosa.load(
                    audio_path, 
                    sr=22050,  # Standard sample rate for music analysis
                    mono=True,  # Convert to mono
                    res_type='kaiser_fast'  # Fast resampling
                )
                
                # Normalize audio to prevent clipping artifacts
                if len(y) > 0:
                    y = librosa.util.normalize(y)
                else:
                    logger.error(f"Empty audio loaded from: {audio_path}")
                    return None
                    
            except Exception as e:
                logger.error(f"Failed to load audio: {e}")
                
                # Try conversion fallback
                if audio_path.endswith('.mp3'):
                    converted_path = self.convert_mp3_to_wav(audio_path)
                    if converted_path != audio_path:
                        try:
                            y, sr = librosa.load(converted_path, sr=22050, mono=True)
                            y = librosa.util.normalize(y)
                        except Exception as inner_e:
                            logger.error(f"Failed to load converted audio: {inner_e}")
                            return None
                    else:
                        return None
                else:
                    return None

            # Ensure minimum audio length (at least 1 second)
            if len(y) < sr:
                logger.warning(f"Audio too short for reliable analysis: {len(y)/sr:.2f}s")
                # Pad with silence if too short
                y = np.pad(y, (0, sr - len(y)), mode='constant')

            logger.info(f"Processing audio: {len(y)/sr:.2f}s at {sr}Hz")

            # Extract features with error handling for each feature type
            features = {}
            
            # 1. Spectral Features
            try:
                # MFCCs (Mel-frequency cepstral coefficients) - most important
                mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
                features['mfccs'] = mfccs
                
                # Spectral centroid (brightness)
                spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
                features['spectral_centroid'] = float(spectral_centroid)
                
                # Spectral bandwidth
                spectral_bandwidth = np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))
                features['spectral_bandwidth'] = float(spectral_bandwidth)
                
                # Spectral contrast
                spectral_contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
                features['spectral_contrast'] = spectral_contrast
                
                # Spectral rolloff (frequency below which 85% of energy is contained)
                spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
                features['spectral_rolloff'] = float(spectral_rolloff)
                
                # Spectral flatness (measure of how noise-like vs. tonal)
                spectral_flatness = np.mean(librosa.feature.spectral_flatness(y=y))
                features['spectral_flatness'] = float(spectral_flatness)
                
                # Zero crossing rate (measure of percussive content)
                zcr = np.mean(librosa.feature.zero_crossing_rate(y))
                features['zero_crossing_rate'] = float(zcr)
                
            except Exception as e:
                logger.error(f"Error extracting spectral features: {e}")
                return None

            # 2. Harmonic Features
            try:
                # Chroma features (harmonic content)
                chroma = librosa.feature.chroma_stft(y=y, sr=sr)
                features['chroma'] = chroma
                
                # Tonnetz (tonal centroid features)
                tonnetz = librosa.feature.tonnetz(y=librosa.effects.harmonic(y), sr=sr)
                features['tonnetz'] = tonnetz
                
            except Exception as e:
                logger.warning(f"Error extracting harmonic features: {e}")
                # Provide fallback values
                features['chroma'] = np.zeros((12, 1))
                features['tonnetz'] = np.zeros((6, 1))

            # 3. Rhythmic Features
            try:
                # Tempo and beat tracking
                tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
                features['tempo'] = float(tempo)
                
                # Beat strength (how strong the beat is)
                if len(beats) > 1:
                    beat_times = librosa.frames_to_time(beats, sr=sr)
                    beat_strength = np.std(np.diff(beat_times))  # Consistency of beats
                else:
                    beat_strength = 0.0
                features['beat_strength'] = float(beat_strength)
                
                # Onset strength (how prominent note onsets are)
                onset_envelope = librosa.onset.onset_strength(y=y, sr=sr)
                onset_strength = np.mean(onset_envelope)
                features['onset_strength'] = float(onset_strength)
                
            except Exception as e:
                logger.warning(f"Error extracting rhythmic features: {e}")
                features['tempo'] = 120.0  # Default tempo
                features['beat_strength'] = 0.0
                features['onset_strength'] = 0.0

            # 4. Dynamic Features
            try:
                # RMS energy (overall loudness)
                rms = librosa.feature.rms(y=y)
                rms_energy = np.mean(rms)
                features['rms_energy'] = float(rms_energy)
                
                # Dynamic range (difference between loudest and quietest parts)
                dynamic_range = np.max(rms) - np.min(rms)
                features['dynamic_range'] = float(dynamic_range)
                
            except Exception as e:
                logger.warning(f"Error extracting dynamic features: {e}")
                features['rms_energy'] = 0.0
                features['dynamic_range'] = 0.0

            # 5. High-level Features (Key and Mode)
            try:
                # Extract key signature and mode using chroma features
                chroma_mean = np.mean(features['chroma'], axis=1)
                
                # Simple key detection using chroma profile correlation
                # This is a basic implementation - more sophisticated methods exist
                key_profiles = np.array([
                    [1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1],  # C major
                    [1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0],  # A minor
                ])
                
                correlations = []
                for key in range(12):
                    # Rotate chroma to test each key
                    rotated_chroma = np.roll(chroma_mean, key)
                    major_corr = np.corrcoef(rotated_chroma, key_profiles[0])[0, 1]
                    minor_corr = np.corrcoef(rotated_chroma, key_profiles[1])[0, 1]
                    correlations.append((key, 1, major_corr))  # major
                    correlations.append((key, 0, minor_corr))  # minor
                
                # Find best key and mode
                best_key, best_mode, _ = max(correlations, key=lambda x: x[2])
                features['key_signature'] = int(best_key)
                features['mode'] = int(best_mode)
                
            except Exception as e:
                logger.warning(f"Error extracting key/mode: {e}")
                features['key_signature'] = 0  # Default to C
                features['mode'] = 1  # Default to major

            # Create AudioFeatures object
            try:
                audio_features = AudioFeatures(
                    mfccs=features['mfccs'],
                    spectral_centroid=features['spectral_centroid'],
                    spectral_bandwidth=features['spectral_bandwidth'],
                    spectral_contrast=features['spectral_contrast'],
                    spectral_rolloff=features['spectral_rolloff'],
                    spectral_flatness=features['spectral_flatness'],
                    zero_crossing_rate=features['zero_crossing_rate'],
                    chroma=features['chroma'],
                    tonnetz=features['tonnetz'],
                    tempo=features['tempo'],
                    beat_strength=features['beat_strength'],
                    onset_strength=features['onset_strength'],
                    rms_energy=features['rms_energy'],
                    dynamic_range=features['dynamic_range'],
                    key_signature=features['key_signature'],
                    mode=features['mode']
                )
                
                # Validate feature vector
                feature_vector = audio_features.to_vector()
                if not np.isfinite(feature_vector).all():
                    logger.warning("Feature vector contains invalid values, cleaning...")
                    feature_vector = np.nan_to_num(feature_vector, nan=0.0, posinf=1.0, neginf=-1.0)
                
                logger.info(f"Successfully extracted {len(feature_vector)} features")
                return audio_features
                
            except Exception as e:
                logger.error(f"Error creating AudioFeatures object: {e}")
                return None

        except Exception as e:
            logger.error(f"Unexpected error in feature extraction: {e}")
            return None

    def calculate_advanced_similarity(self, reference_features: AudioFeatures, 
                                  comparison_features: list[AudioFeatures]) -> list[float]:
        """Calculate similarity using weighted feature importance and multiple metrics"""
        if not comparison_features:
            return []

        try:
            # Convert to vectors and clean
            ref_vector = np.nan_to_num(reference_features.to_vector(), nan=0.0, posinf=1.0, neginf=-1.0)
            comp_vectors = np.array([
                np.nan_to_num(f.to_vector(), nan=0.0, posinf=1.0, neginf=-1.0)
                for f in comparison_features
            ])
            
            # Scale features
            all_vectors = np.vstack([ref_vector.reshape(1, -1), comp_vectors])
            scaled_vectors = self.scaler.fit_transform(all_vectors)
            ref_scaled = scaled_vectors[0]
            comp_scaled = scaled_vectors[1:]
            
            # Set weights
            weights = {
                'cosine': 0.4,
                'correlation': 0.3,
                'euclidean': 0.3
            }

            if reference_features.tempo > 150:
                weights['euclidean'] += 0.1
                total = sum(weights.values())
                weights = {k: v / total for k, v in weights.items()}

            similarities = []

            for comp_vector in comp_scaled:
                # 1. Cosine similarity
                cosine_sim = cosine_similarity([ref_scaled], [comp_vector])[0, 0]
                
                # 2. Euclidean similarity
                euclidean_dist = np.linalg.norm(ref_scaled - comp_vector)
                euclidean_sim = 1 / (1 + euclidean_dist)
                
                # 3. Correlation
                try:
                    correlation, _ = pearsonr(ref_scaled, comp_vector)
                except Exception:
                    correlation = 0.0

                # Weighted similarity
                weighted_sim = (
                    weights['cosine'] * cosine_sim +
                    weights['correlation'] * correlation +
                    weights['euclidean'] * euclidean_sim
                )

                final_similarity = float(np.clip(weighted_sim, 0.0, 1.0))
                similarities.append(final_similarity)

            return similarities

        except Exception as e:
            logger.error(f"Error calculating advanced similarity: {e}")
            return [0.5] * len(comparison_features)

# Legacy compatibility function
def extract_audio_features(audio_path: str) -> Optional[np.ndarray]:
    """Legacy function that returns a simple feature vector for backwards compatibility"""
    processor = EnhancedAudioProcessor()
    features = processor.extract_comprehensive_features(audio_path)
    
    if features:
        return features.to_vector()
    return None