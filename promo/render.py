"""Xuất promo/intro-clip.html ra MP4 1920x1080, 30fps.

Cách dùng:
    python promo/render.py                      # xuất promo/tin-portfolio-intro.mp4
    python promo/render.py --stills 4.5,9,17    # chỉ chụp vài khung hình PNG để soát

Cần: pip install playwright imageio-ffmpeg  (và `playwright install chromium` nếu chưa có)
"""
import argparse
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PAGE = (HERE / "intro-clip.html").as_uri() + "?render"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--out", default=str(HERE / "tin-portfolio-intro.mp4"))
    ap.add_argument("--stills", help="danh sách giây, cách nhau dấu phẩy")
    ap.add_argument("--stills-dir", default=str(HERE / "stills"))
    args = ap.parse_args()

    with sync_playwright() as p:
        # dùng Chromium của Playwright nếu có, không thì mượn Edge / Chrome đã cài sẵn trên máy
        for opts in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
            try:
                browser = p.chromium.launch(**opts)
                break
            except Exception:
                continue
        else:
            sys.exit("Không mở được trình duyệt: chạy `python -m playwright install chromium`")
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(PAGE, wait_until="networkidle")
        page.evaluate("window.ready")
        duration = page.evaluate("window.DURATION")

        if args.stills:
            out = Path(args.stills_dir)
            out.mkdir(exist_ok=True)
            for s in args.stills.split(","):
                t = float(s)
                page.evaluate(f"seek({t})")
                page.screenshot(path=str(out / f"t{t:05.1f}.png"))
                print("saved", out / f"t{t:05.1f}.png")
            browser.close()
            return

        frames = int(duration * args.fps)
        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
            "-f", "image2pipe", "-framerate", str(args.fps), "-c:v", "mjpeg", "-i", "-",
            "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-movflags", "+faststart", args.out,
        ]
        ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for i in range(frames):
            page.evaluate(f"seek({i / args.fps})")
            ff.stdin.write(page.screenshot(type="jpeg", quality=93))
            if i % args.fps == 0:
                print(f"\r{i // args.fps}/{int(duration)}s", end="", flush=True)
        ff.stdin.close()
        ff.wait()
        browser.close()
        print("\nxong:", args.out)
        sys.exit(ff.returncode)


if __name__ == "__main__":
    main()
