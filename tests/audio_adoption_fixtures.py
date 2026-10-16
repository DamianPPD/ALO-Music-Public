"""Real synthetic music fixtures; never use a person's music library."""
import math
from pathlib import Path
import shutil
import struct
import subprocess
import wave
from io import BytesIO

import pytest
from PIL import Image
from mutagen.id3 import ID3, TIT2, TPE1, APIC


@pytest.fixture(scope='session')
def mp3_samples(tmp_path_factory):
    directory = tmp_path_factory.mktemp('adoption-audio')
    results = {}
    for name in ('original', 'different_tail'):
        wav = directory / f'{name}.wav'
        rate = 44100
        with wave.open(str(wav), 'wb') as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(rate)
            data = bytearray()
            for i in range(rate * 2):
                frequency = 880 if name == 'different_tail' and i > rate * 1.6 else 440
                value = int(12000 * math.sin(2 * math.pi * frequency * i / rate))
                data.extend(struct.pack('<hh', value, value // 2))
            writer.writeframes(data)
        mp3 = directory / f'{name}.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(wav),
                        '-c:a', 'libmp3lame', '-b:a', '128k', str(mp3)],
                       check=True, capture_output=True, timeout=20)
        results[name] = mp3
    return results


def copy_audio(sample, path, *, title=None, cover=False, id3_version=4):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sample, path)
    if title is not None or cover:
        tags = ID3(path)
        if title is not None:
            tags.add(TIT2(encoding=3, text=[title]))
            tags.add(TPE1(encoding=3, text=['Fixture artist']))
        if cover:
            image = BytesIO()
            Image.new('RGB', (8, 8), (20, 40, 80)).save(image, format='PNG')
            tags.add(APIC(encoding=3, mime='image/png', type=3, desc='', data=image.getvalue()))
        tags.save(path, v2_version=id3_version)
    return path
