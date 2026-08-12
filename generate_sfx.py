import math
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SFX_DIR = ROOT / "assets" / "sfx"
SAMPLE_RATE = 44100


def envelope(index, total):
    attack = max(1, int(total * 0.08))
    release = max(1, int(total * 0.30))
    if index < attack:
        return index / attack
    if index > total - release:
        return max(0.0, (total - index) / release)
    return 1.0


def synth(path, notes, duration=0.22, volume=0.45, noise=0.0):
    total = int(SAMPLE_RATE * duration)
    frames = bytearray()
    for i in range(total):
        t = i / SAMPLE_RATE
        value = 0.0
        for freq, weight in notes:
            value += math.sin(2 * math.pi * freq * t) * weight
        if noise:
            value += ((math.sin(i * 12.9898) * 43758.5453) % 1.0 - 0.5) * noise
        value *= envelope(i, total) * volume
        sample = int(max(-1.0, min(1.0, value)) * 32767)
        frames.extend(struct.pack("<hh", sample, sample))

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(frames)


def main():
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    sounds = {
        "convert_01.wav": ([(170, 0.8), (95, 0.35)], 0.14, 0.40, 0.35),
        "spawn_rock.wav": ([(120, 0.8), (240, 0.25)], 0.16, 0.34, 0.10),
        "spawn_paper.wav": ([(360, 0.55), (540, 0.35)], 0.16, 0.34, 0.05),
        "spawn_scissors.wav": ([(640, 0.45), (900, 0.25)], 0.12, 0.30, 0.18),
        "gift_small.wav": ([(760, 0.45), (1140, 0.25)], 0.20, 0.35, 0.02),
        "gift_medium.wav": ([(420, 0.35), (630, 0.35), (840, 0.25)], 0.38, 0.45, 0.04),
        "gift_large.wav": ([(90, 0.55), (180, 0.35), (360, 0.25)], 0.72, 0.55, 0.12),
        "power_up.wav": ([(520, 0.35), (780, 0.35), (1040, 0.25)], 0.45, 0.42, 0.02),
        "win_rock.wav": ([(180, 0.45), (270, 0.35), (360, 0.25)], 0.80, 0.45, 0.03),
        "win_paper.wav": ([(300, 0.35), (450, 0.35), (600, 0.25)], 0.80, 0.45, 0.03),
        "win_scissors.wav": ([(420, 0.35), (630, 0.35), (840, 0.25)], 0.80, 0.45, 0.04),
        "countdown.wav": ([(880, 0.45)], 0.10, 0.35, 0.00),
        "reset.wav": ([(220, 0.35), (330, 0.35), (440, 0.25)], 0.35, 0.36, 0.02),
    }
    for filename, (notes, duration, volume, noise) in sounds.items():
        synth(SFX_DIR / filename, notes, duration, volume, noise)
    print(f"Generated {len(sounds)} SFX files in {SFX_DIR}")


if __name__ == "__main__":
    main()
