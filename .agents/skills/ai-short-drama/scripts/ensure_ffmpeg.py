# -*- coding: utf-8 -*-
r"""ffmpeg 自动供给: 检测不到时下载静态版到 <数据根>/tools/ffmpeg/
用法:
    python ensure_ffmpeg.py            # 检测+缺失自动下载
    python ensure_ffmpeg.py --check    # 只查状态(JSON)
下载源(按序尝试, config.json 的 ffmpeg_url 可覆盖; proxy 键可配代理):
    Windows: gyan.dev / BtbN(GitHub)
    Linux:   johnvansickle.com 静态版
    macOS:   evermeet.cx
仅标准库。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wsroot import ws_root

sys.stdout.reconfigure(encoding="utf-8")
ROOT = ws_root()
DEST = os.path.join(ROOT, "tools", "ffmpeg")
IS_WIN = sys.platform == "win32"

SOURCES = {
    "win32": [
        {"name": "gyan.dev", "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", "kind": "zip-bin"},
        {"name": "BtbN", "url": "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip", "kind": "zip-bin"},
    ],
    "linux": [
        {"name": "johnvansickle", "url": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz", "kind": "tarxz-bin"},
    ],
    "darwin": [
        {"name": "evermeet", "url": "https://evermeet.cx/ffmpeg/get|https://evermeet.cx/ffprobe/get", "kind": "zip-root"},
    ],
}


def load_cfg():
    p = os.path.join(ROOT, "config.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def make_opener(cfg):
    proxy = cfg.get("proxy", "")
    if proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener()


def download(url, dst, opener):
    print("下载: " + url)
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120) as r, open(dst, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total and got % (10 << 20) < (1 << 20):
                print("  %d/%d MB" % (got >> 20, total >> 20))
    print("  完成, %.1f MB" % (os.path.getsize(dst) / 1048576))


def extract_bin(archive, kind, exe_names):
    """从压缩包里抠出 ffmpeg/ffprobe 可执行文件, 返回是否成功"""
    os.makedirs(DEST, exist_ok=True)
    if kind == "zip-root":  # evermeet: 每个 zip 根目录就是一个二进制(调用方逐个处理)
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                base = os.path.basename(n)
                if base in exe_names:
                    with z.open(n) as src, open(os.path.join(DEST, base), "wb") as dst:
                        shutil.copyfileobj(src, dst)
        return True
    want = set(exe_names)
    if kind == "zip-bin":
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                base = os.path.basename(n)
                if base in want and ("/bin/" in n.replace("\\", "/") or base == n):
                    with z.open(n) as src, open(os.path.join(DEST, base), "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    want.discard(base)
    elif kind == "tarxz-bin":
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                base = os.path.basename(m.name)
                if base in want and m.isfile():
                    f = t.extractfile(m)
                    with open(os.path.join(DEST, base), "wb") as dst:
                        shutil.copyfileobj(f, dst)
                    os.chmod(dst.name, 0o755)
                    want.discard(base)
    return not want


def verify():
    exe = os.path.join(DEST, "ffmpeg.exe" if IS_WIN else "ffmpeg")
    if not os.path.exists(exe):
        return False, "ffmpeg 不在 tools/"
    try:
        r = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=30)
        ver = (r.stdout or "").splitlines()[0] if r.stdout else ""
        return r.returncode == 0, ver
    except Exception as e:
        return False, str(e)[:120]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--force", action="store_true", help="即使 PATH/本地已有也重新下载(修复损坏)")
    a = ap.parse_args()

    in_path = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
    local_ok = False
    if os.path.exists(os.path.join(DEST, "ffmpeg.exe" if IS_WIN else "ffmpeg")):
        local_ok, _ = verify()
    if a.check:
        print(json.dumps({"in_path": in_path, "local": local_ok, "dir": DEST,
                          "ok": in_path or local_ok}, ensure_ascii=False))
        return

    if in_path and not a.force:
        print(json.dumps({"ok": True, "source": "PATH"}, ensure_ascii=False))
        return
    if local_ok and not a.force:
        ok, ver = verify()
        print(json.dumps({"ok": True, "source": "local", "version": ver}, ensure_ascii=False))
        return

    cfg = load_cfg()
    opener = make_opener(cfg)
    exe_names = ["ffmpeg.exe", "ffprobe.exe"] if IS_WIN else ["ffmpeg", "ffprobe"]
    candidates = list(SOURCES.get(sys.platform, []))
    if cfg.get("ffmpeg_url"):
        candidates.insert(0, {"name": "config", "url": cfg["ffmpeg_url"],
                              "kind": "tarxz-bin" if cfg["ffmpeg_url"].endswith((".tar.xz", ".tar.gz")) else "zip-bin"})
    tmp = os.path.join(ROOT, "tools", "_ffmpeg_dl")
    os.makedirs(tmp, exist_ok=True)
    errors = []
    for src in candidates:
        urls = src["url"].split("|")
        try:
            archives = []
            for i, u in enumerate(urls):
                dst = os.path.join(tmp, "dl_%d" % i)
                download(u, dst, opener)
                archives.append(dst)
            names = exe_names if src["kind"] != "zip-root" else \
                [[n] for n in exe_names]
            if src["kind"] == "zip-root":
                for arc, nm in zip(archives, names):
                    extract_bin(arc, "zip-root", nm)
                ok = all(os.path.exists(os.path.join(DEST, n)) for n in exe_names)
            else:
                ok = extract_bin(archives[0], src["kind"], exe_names)
            if not ok:
                errors.append(src["name"] + ": 压缩包里没找到 ffmpeg/ffprobe")
                continue
            good, ver = verify()
            if good:
                shutil.rmtree(tmp, ignore_errors=True)
                print(json.dumps({"ok": True, "source": src["name"], "dir": DEST, "version": ver}, ensure_ascii=False))
                return
            errors.append(src["name"] + ": " + ver)
        except Exception as e:
            errors.append(src["name"] + ": " + str(e)[:150])
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"ok": False, "errors": errors,
                      "hint": "可手动安装 ffmpeg 到 PATH, 或在 config.json 配 ffmpeg_url/proxy 指向可达镜像后重跑"}, ensure_ascii=False))
    sys.exit(1)


if __name__ == "__main__":
    main()
