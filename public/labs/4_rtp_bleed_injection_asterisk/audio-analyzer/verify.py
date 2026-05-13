import sys
import numpy as np
from scipy.io import wavfile
from scipy.stats import gmean

def analyze_injection(file_path):
    try:
        # Load audio
        sr, data = wavfile.read(file_path)
        
        # Convert to float and normalize
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        elif data.dtype == np.uint8:
            data = (data.astype(np.float32) - 128.0) / 128.0

        # Ensure Mono
        if len(data.shape) > 1: 
            data = data[:, 0]

        # Calculate Power Spectral Density
        fft = np.abs(np.fft.rfft(data))
        psd = fft**2 + 1e-10  # Add small epsilon to avoid log(0)

        # Spectral Flatness = Geometric Mean / Arithmetic Mean
        # Tonal signals (beeps) are near 0, Noisy signals (injection) are high
        flatness = gmean(psd) / np.mean(psd)
        
        # Calculate RMS Energy
        rms = np.sqrt(np.mean(data**2))

        print(f"[*] Analysis Results for: {file_path}")
        print(f"[*] Spectral Flatness: {flatness:.6f}")
        print(f"[*] RMS Energy: {rms:.6f}")

        # THRESHOLD LOGIC
        # buono.wav flatness is typically < 0.001
        # injected.wav flatness is typically > 0.05
        if flatness > 0.01 or rms > 0.10:
            print("✅ [CONFIRMED] RTP Injection Detected! (High noise/energy floor)")
            sys.exit(0)
        else:
            print("❌ [CLEAN] No injection detected. (Tonal/Sparse signal)")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify.py <path_to_wav>")
        sys.exit(1)
    analyze_injection(sys.argv[1])