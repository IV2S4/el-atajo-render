"""
Música de fondo lo-fi generada por código (100% propia, sin derechos de autor).
Cada video sale con una canción distinta (tono, tempo y acordes al azar).

Uso:  python musica.py segundos salida.wav [semilla]
"""
import sys, wave
import numpy as np

SR = 44100


def nota(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def lowpass(x, corte):
    """Filtro pasa-bajos simple de 1 polo (suaviza el sonido)."""
    a = np.exp(-2 * np.pi * corte / SR)
    y = np.empty_like(x)
    acc = 0.0
    b = 1 - a
    for i in range(len(x)):  # rápido de sobra para ~1 min
        acc = b * x[i] + a * acc
        y[i] = acc
    return y


def env(n, ataque, caida):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(ataque, 1e-4)) * np.exp(-t / caida)
    return e


def piano(freq, dur, vel=0.5):
    """Piano eléctrico suave (tipo Rhodes)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 3)
         + 0.12 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t * 6))
    trem = 1 + 0.08 * np.sin(2 * np.pi * 4.5 * t)
    return s * env(n, 0.006, 1.2) * trem * vel


def pad(freqs, dur):
    """Colchón de acordes suave y ancho."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for f in freqs:
        for d in (-0.12, 0.12):
            ph = 2 * np.pi * f * (1 + d / 100) * t
            s += np.sin(ph) + 0.25 * np.sin(2 * ph)
    s /= max(1, len(freqs) * 2)
    fade = np.minimum(1, np.minimum(t / 0.6, (dur - t) / 0.6))
    return s * np.clip(fade, 0, 1) * 0.35


def bajo(freq, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(4 * np.pi * freq * t)
    return s * env(n, 0.01, 0.45) * 0.55


def bombo(rng):
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 110 * np.exp(-t * 18) + 45
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * 0.9


def caja(rng):
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    ruido = rng.standard_normal(n)
    ruido = ruido - lowpass(ruido, 1200)  # quita graves
    return (0.45 * ruido * np.exp(-t * 22) + 0.3 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)) * 0.5


def platillo(rng, abierto=False):
    n = int((0.25 if abierto else 0.07) * SR)
    t = np.arange(n) / SR
    r = rng.standard_normal(n)
    r = r - lowpass(r, 6000)
    return r * np.exp(-t * (12 if abierto else 60)) * 0.18


PROGRESIONES = [
    [0, 7, 9, 5],     # I  V  vi IV
    [9, 5, 0, 7],     # vi IV I  V
    [2, 7, 0, 9],     # ii V  I  vi
    [0, 9, 5, 7],     # I  vi IV V
    [5, 7, 4, 9],     # IV V  iii vi
]


def acorde(grado, tonica):
    menores = {2, 4, 9}
    raiz = tonica + grado
    tercera = 3 if grado in menores else 4
    return [raiz, raiz + tercera, raiz + 7, raiz + 11 if grado not in menores else raiz + 10]


def pegar(buf, x, pos):
    if pos >= len(buf):
        return
    fin = min(len(buf), pos + len(x))
    buf[pos:fin] += x[:fin - pos]


def generar(segundos, semilla=None):
    rng = np.random.default_rng(semilla)
    bpm = int(rng.integers(78, 92))
    tonica = 57 + int(rng.integers(0, 7))          # La3 .. Mi4 aprox
    prog = PROGRESIONES[int(rng.integers(0, len(PROGRESIONES)))]
    beat = 60 / bpm
    compas = 4 * beat
    swing = beat * 0.08
    total = int((segundos + 1) * SR)
    mus = np.zeros(total)
    bat = np.zeros(total)
    n_comp = int(np.ceil(segundos / compas)) + 1

    k, s, hc, ho = bombo(rng), caja(rng), platillo(rng), platillo(rng, True)
    for c in range(n_comp):
        t0 = c * compas
        notas = acorde(prog[c % 4], tonica)
        freqs = [nota(m) for m in notas]
        pegar(mus, pad([nota(m - 12) for m in notas[:3]], compas + 0.3), int(t0 * SR))
        # piano: acorde en tiempo 1 y "y" del 3, con arpegio suave
        for i, f in enumerate(freqs):
            pegar(mus, piano(f, 1.8, 0.16), int((t0 + i * 0.018) * SR))
            pegar(mus, piano(f, 1.2, 0.10), int((t0 + 2.5 * beat + i * 0.02) * SR))
        # bajo
        raiz = nota(notas[0] - 24)
        pegar(mus, bajo(raiz, beat * 1.6), int(t0 * SR))
        pegar(mus, bajo(raiz, beat * 1.2), int((t0 + 2.5 * beat) * SR))
        # batería (entra después del primer compás)
        if c == 0:
            continue
        for b in range(4):
            tb = t0 + b * beat
            if b in (0, 2):
                pegar(bat, k, int(tb * SR))
            if b in (1, 3):
                pegar(bat, s, int(tb * SR))
            pegar(bat, hc, int(tb * SR))
            pegar(bat, hc * 0.7, int((tb + beat / 2 + swing) * SR))
        if c % 4 == 3:
            pegar(bat, ho, int((t0 + 3.5 * beat + swing) * SR))

    mus = lowpass(mus, 2600)  # sonido "lo-fi" cálido
    mezcla = mus + bat * 0.8
    # "vinilo": ruido suave
    mezcla += lowpass(rng.standard_normal(total), 3000) * 0.004
    mezcla = mezcla[: int(segundos * SR)]
    mezcla /= (np.max(np.abs(mezcla)) + 1e-9)
    mezcla *= 0.5
    return mezcla.astype(np.float32)


def guardar(path, audio):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    est = np.stack([pcm, pcm], axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(est.tobytes())


if __name__ == "__main__":
    seg = float(sys.argv[1])
    semilla = int(sys.argv[3]) if len(sys.argv) > 3 else None
    guardar(sys.argv[2], generar(seg, semilla))
    print("musica lista", sys.argv[2])
