"""Thêm giọng thuyết minh (nam, tiếng Việt) + nhạc nền + hiệu ứng vào clip.

    python promo/audio.py            # tạo lại giọng đọc rồi mix → tin-portfolio-intro-voice.mp4
    python promo/audio.py --no-tts   # dùng lại giọng đã tạo trong promo/voice/

Giọng đọc: Microsoft Edge TTS (vi-VN-NamMinhNeural) qua gói edge-tts.
Nhạc nền & hiệu ứng: tự tổng hợp bằng numpy (không dùng nhạc có bản quyền).
"""
import argparse
import sys
import asyncio
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

HERE = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")
FF = imageio_ffmpeg.get_ffmpeg_exe()
SR = 44100
DUR = 65.5
VOICE = "vi-VN-NamMinhNeural"

# (bắt đầu, thời lượng tối đa, lời đọc) — khớp với 7 cảnh trong intro-clip.html
LINES = [
    (0.5, 5.2, "Hello cả nhà, Tín đây! Mình vừa làm xong cái portfolio riêng nè."),
    (6.3, 6.3, "Mình là Thành Tín, dân ai-ti văn phòng hệ Gen Z, đang làm việc ở Sài Gòn."),
    (13.3, 7.3, "Ban ngày thì viết code, fix bug, họp hành, và ráng sống sót qua deadline, nhờ ba ly cà phê."),
    (21.3, 6.5, "Ban đêm thì lên Threads viết caption. Có bài được tới bốn mươi chín nghìn tim luôn á!"),
    (28.5, 9.2, "Nên mình gom hết vào một chỗ, làm giống cái desktop văn phòng: có góc công việc chuyên môn, shop bán đồ decor, và mục booking nếu các brand có nhu cầu hợp tác."),
    (38.4, 8.0, "Ngoài ra, bạn còn xem được giá vàng và vi-en in-đếch ngay trên desktop này luôn. Mình sẽ cập nhật thêm những thứ hay ho khác lên đây nữa."),
    (47.0, 7.3, "Có cả mấy món đồ chơi nhỏ: kéo chữ, hỏi vị thần quyết định, hay mời mình một ly cà phê."),
    (55.0, 10.2, "Web đang chạy tạm trên tên miền miễn phí của GitHub, có tiền mua tên miền Tín đổi sau nha. Team bạn đang cần người? Tín đang open to work đó!"),
]


# ---------------------------------------------------------------- tiện ích âm thanh
def decode(path):
    """Giải mã file âm thanh bất kỳ thành mảng float mono 44.1kHz."""
    raw = subprocess.run([FF, "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def trim_silence(x, thr=0.01):
    idx = np.where(np.abs(x) > thr)[0]
    return x[max(0, idx[0] - 600): idx[-1] + 2000] if len(idx) else x


def env(n, a=0.005, r=None):
    """Đường bao attack nhanh + decay hàm mũ."""
    t = np.arange(n) / SR
    e = np.minimum(1, t / a)
    return e * (np.exp(-t / r) if r else 1)


def add(buf, sig, t, gain=1.0):
    i = int(t * SR)
    if i >= len(buf):
        return
    sig = sig[: len(buf) - i]
    buf[i: i + len(sig)] += sig * gain


def lowpass(x, cutoff):
    # bộ lọc 1 cực đơn giản
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    s = 0.0
    for i, v in enumerate(x):
        s = (1 - a) * v + a * s
        y[i] = s
    return y


rng = np.random.default_rng(7)


# ---------------------------------------------------------------- nhạc nền
def note(freq, dur, kind="ep"):
    n = int(dur * SR)
    t = np.arange(n) / SR
    if kind == "ep":      # electric piano mềm
        s = np.sin(2 * np.pi * freq * t) + .35 * np.sin(4 * np.pi * freq * t) + .12 * np.sin(6 * np.pi * freq * t)
        return s * env(n, .006, .55)
    if kind == "bass":
        s = np.sin(2 * np.pi * freq * t) + .25 * np.sin(4 * np.pi * freq * t)
        return s * env(n, .004, .35)
    if kind == "pluck":
        s = np.sign(np.sin(2 * np.pi * freq * t)) * .3 + np.sin(2 * np.pi * freq * t)
        return s * env(n, .002, .14)
    if kind == "pad":
        s = sum(np.sin(2 * np.pi * freq * d * t) for d in (1, 1.004, .996))
        e = np.minimum(1, t / .6) * np.minimum(1, (dur - t) / .6)
        return s * e / 3
    raise ValueError(kind)


def kick():
    n = int(.35 * SR); t = np.arange(n) / SR
    f = 50 + 90 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, .001, .12)


def clap():
    n = int(.2 * SR)
    return rng.normal(0, 1, n) * env(n, .001, .05) * .6


def hat():
    n = int(.06 * SR)
    x = rng.normal(0, 1, n)
    x = x - lowpass(x, 6000)
    return x * env(n, .0005, .018)


def midi(m):
    return 440 * 2 ** ((m - 69) / 12)


def music():
    bpm = 112
    beat = 60 / bpm
    bar = 4 * beat
    out = np.zeros(int(DUR * SR) + SR)
    # C – Am – F – G (giọng Đô trưởng, vui & nhẹ)
    prog = [(60, [60, 64, 67, 71]), (57, [57, 60, 64, 67]), (53, [53, 57, 60, 64]), (55, [55, 59, 62, 65])]
    penta = [72, 74, 76, 79, 81, 84]
    K, C, H = kick(), clap(), hat()
    nbars = int(DUR / bar) + 1
    for b in range(nbars):
        t0 = b * bar
        root, chord = prog[b % 4]
        night = 20.6 <= t0 < 28.0          # cảnh ban đêm: bỏ trống, chỉ pad + piano thưa
        intro = t0 < bar * 1                # ô nhịp đầu: vào nhẹ
        if night:
            for m in chord:
                add(out, note(midi(m), bar, "pad"), t0, .05)
            add(out, note(midi(root - 12), bar * .9, "bass"), t0, .08)
            for k, m in enumerate(chord):
                add(out, note(midi(m + 12), 1.2, "ep"), t0 + k * beat, .045)
            continue
        # piano: hợp âm đánh nhịp 1 và nhịp "và" của 2
        for hit in (0, 1.5, 2.5):
            for m in chord:
                add(out, note(midi(m), beat * 1.6, "ep"), t0 + hit * beat, .05)
        # bass
        for hit, off in ((0, 0), (1.5, 0), (2, 7), (3, 0)):
            add(out, note(midi(root - 24 + off), beat * .9, "bass"), t0 + hit * beat, .22)
        if not intro:
            for k in range(4):
                if k in (0, 2):
                    add(out, K, t0 + k * beat, .55)
                if k in (1, 3):
                    add(out, C, t0 + k * beat, .16)
            for k in range(8):
                add(out, H, t0 + k * beat / 2, .10 if k % 2 else .06)
            # giai điệu pluck ngẫu nhiên trong ngũ cung (cố định seed nên lần nào cũng giống nhau)
            for k in range(8):
                if rng.random() < .55:
                    add(out, note(midi(rng.choice(penta)), .3, "pluck"), t0 + k * beat / 2, .035)
    # fade in/out
    n = len(out)
    t = np.arange(n) / SR
    out *= np.minimum(1, t / 1.0) * np.clip((DUR + .2 - t) / 2.5, 0, 1)
    return out[: int(DUR * SR)]


# ---------------------------------------------------------------- hiệu ứng
def sfx_pop(f=900):
    n = int(.12 * SR); t = np.arange(n) / SR
    fr = f * (1 + 1.5 * np.exp(-t * 60))
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * env(n, .001, .03)


def sfx_click():
    n = int(.03 * SR)
    x = rng.normal(0, 1, n)
    return (x - lowpass(x, 2500)) * env(n, .0003, .006)


def sfx_whoosh(d=.5):
    n = int(d * SR); t = np.arange(n) / SR
    x = rng.normal(0, 1, n)
    x = lowpass(x, 1800)
    return x * np.sin(np.pi * t / d) ** 2 * 1.4


def sfx_ding(f=1568):
    n = int(.6 * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) + .4 * np.sin(2 * np.pi * f * 2.01 * t)) * env(n, .002, .18)


def sfx_chime():
    out = np.zeros(int(1.4 * SR))
    for k, m in enumerate([84, 88, 91, 96]):
        add(out, sfx_ding(midi(m)), k * .09, .5)
    return out


def sfx():
    out = np.zeros(int(DUR * SR))
    # cảnh 1: từng chữ bật lên + chấm rơi
    for i in range(9):
        add(out, sfx_pop(700 + i * 60), .55 + i * .09 + .25, .18)
    add(out, sfx_ding(1318), 1.55 + .4, .12)
    # chuyển cảnh
    for t in (5.75, 12.65, 20.65, 27.85, 37.75, 46.35, 54.35):
        add(out, sfx_whoosh(), t, .10)
    # cảnh 2: avatar + chip + polaroid
    add(out, sfx_pop(500), 6.5, .25)
    for t in (7.9, 8.15, 8.4, 8.65):
        add(out, sfx_pop(1000), t + .1, .12)
    # cảnh 3: gõ phím + tick to-do
    t = 14.0
    while t < 19.1:
        add(out, sfx_click(), t, .22 * (.6 + .4 * rng.random()))
        t += .06 + .07 * rng.random()
    for t in (15.25, 16.15, 17.05, 18.35):
        add(out, sfx_ding(1760), t, .10)
    # cảnh 4: gõ caption + tim
    t = 22.2
    while t < 26.2:
        add(out, sfx_click(), t, .18 * (.6 + .4 * rng.random()))
        t += .07 + .08 * rng.random()
    for k in range(10):
        add(out, sfx_pop(1200 + 80 * k), 24.6 + k * .3, .07)
    # cảnh 5: zone + dock + nhấp đúp mở cửa sổ
    for t in (28.6, 28.85, 29.1, 29.35):
        add(out, sfx_pop(650), t + .1, .14)
    for k in range(7):
        add(out, sfx_pop(900 + 70 * k), 29.75 + k * .1, .08)
    for t in (32.15, 33.15, 34.7):          # con trỏ chọn từng zone
        add(out, sfx_click(), t, .6)
        add(out, sfx_pop(820), t + .02, .12)
    # cảnh 5b: tiện ích giá vàng / VN-Index
    for t in (38.5, 38.8):
        add(out, sfx_pop(600), t + .1, .15)
    for t in (39.7, 39.95, 40.2):
        add(out, sfx_pop(1150), t, .07)
    add(out, sfx_chime(), 41.7, .14)
    add(out, sfx_pop(700), 43.9, .15)
    # cảnh 6: kéo chữ, mở sách, cà phê
    for t in (47.2, 47.45, 47.7):
        add(out, sfx_pop(600), t + .1, .15)
    add(out, sfx_click(), 47.95, .5); add(out, sfx_click(), 49.05, .5)
    add(out, sfx_click(), 49.85, .5); add(out, sfx_chime(), 50, .22)
    add(out, sfx_click(), 51.65, .5)
    for k in range(8):
        add(out, sfx_pop(1100 + 90 * k), 51.7 + k * .25, .08)
    # cảnh 7
    add(out, sfx_pop(500), 55.2, .25)
    for i in range(9):
        add(out, sfx_pop(700 + i * 60), 55.8 + i * .07 + .2, .12)
    add(out, sfx_chime(), 56.8, .18)
    return out


# ---------------------------------------------------------------- giọng đọc
async def tts_all(vdir):
    import edge_tts
    vdir.mkdir(exist_ok=True)
    for i, (_, maxd, text) in enumerate(LINES):
        rate = 8
        while True:
            path = vdir / f"line{i + 1}.mp3"
            for attempt in range(5):         # dịch vụ thỉnh thoảng trả về rỗng, thử lại
                try:
                    await edge_tts.Communicate(text, VOICE, rate=f"+{rate}%", pitch="+0Hz").save(str(path))
                    break
                except edge_tts.exceptions.NoAudioReceived:
                    if attempt == 4:
                        raise
                    await asyncio.sleep(2 + attempt * 2)
            d = len(trim_silence(decode(path))) / SR
            print(f"câu {i + 1}: {d:.2f}s (tối đa {maxd}s, tốc độ +{rate}%)")
            if d <= maxd or rate >= 40:
                break
            rate += 7


def voice_track(vdir):
    out = np.zeros(int(DUR * SR))
    for i, (t, _, _) in enumerate(LINES):
        v = trim_silence(decode(vdir / f"line{i + 1}.mp3"))
        v = v / (np.abs(v).max() + 1e-9) * .9
        add(out, v, t)
    return out


def write_wav(path, x):
    x = np.clip(x, -1, 1)
    pcm = (np.stack([x, x], 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tts", action="store_true")
    ap.add_argument("--video", default=str(HERE / "tin-portfolio-intro.mp4"))
    ap.add_argument("--out", default=str(HERE / "tin-portfolio-intro-voice.mp4"))
    args = ap.parse_args()
    vdir = HERE / "voice"
    if not args.no_tts:
        asyncio.run(tts_all(vdir))

    voice = voice_track(vdir)
    mus = music()
    fx = sfx()
    # nhạc tự hạ xuống khi có giọng đọc (ducking)
    level = np.convolve(np.abs(voice), np.ones(4410) / 4410, mode="same")
    duck = 1 - .6 * np.clip(level / .05, 0, 1)
    duck = np.convolve(duck, np.ones(8820) / 8820, mode="same")
    mix = voice * 1.0 + mus * .55 * duck + fx * .8
    mix = mix / max(1.0, np.abs(mix).max() / .95)
    wav = HERE / "voice" / "mix.wav"
    write_wav(wav, mix)
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", args.video, "-i", str(wav),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart", args.out], check=True)
    print("xong:", args.out)


if __name__ == "__main__":
    main()
