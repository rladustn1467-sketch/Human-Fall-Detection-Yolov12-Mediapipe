"""Copy the server and web app into the deployment repository (github.com/rladustn1467-sketch/fall).

Fix code in this repository, then run this and push the deployment repository. Do not edit that one by hand.
  python tools/export_deploy.py <deployment repository folder>

Only files tracked by git are copied, so .env, the database, photos and tokens cannot come along.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRAS = {"deploy/school/README.md": "README.md", "deploy/school/gitignore": ".gitignore",
          "deploy/school/env.example": ".env.example"}
SKIP_PARTS = ("tests",)
SKIP_NAMES = (".env.example",     # 배포용 설정 예시(deploy/school/env.example)로 대신함
              "dev.html", "dev.js")   # 개발 확인용 화면
SKIP_SUFFIXES = (".bat",)
FORBIDDEN_NAMES = (".env", "fall.db", "events.json", "residents.json", "access_token.txt", "telegram_state.json",
                   "google-services.json")
FORBIDDEN_SUFFIXES = (".pem", ".key", ".jks", ".keystore", ".db", ".pt", ".log")
SECRETS = (re.compile(rb"\b\d{8,10}:[A-Za-z0-9_-]{30,}"),      # 텔레그램 봇 토큰
           re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),             # Google API 키
           re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
           re.compile(rb"\"private_key\"\s*:\s*\"[^\"]"),
           re.compile(rb"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b"))   # Tailscale 주소


def server_files(root=ROOT):
    names = subprocess.run(["git", "-C", str(root), "ls-files", "server"], capture_output=True, text=True,
                           encoding="utf-8", check=True).stdout.splitlines()
    for name in names:
        rel = Path(name).relative_to("server")
        if set(rel.parts) & set(SKIP_PARTS) or rel.name in SKIP_NAMES or rel.suffix in SKIP_SUFFIXES:
            continue
        if (root / name).exists():
            yield root / name, rel


def problems(folder):
    found = []
    for path in Path(folder).rglob("*"):
        if not path.is_file() or ".git" in path.relative_to(folder).parts:
            continue
        rel = path.relative_to(folder)
        if path.name in FORBIDDEN_NAMES or path.suffix in FORBIDDEN_SUFFIXES:
            found.append(f"올리면 안 되는 파일: {rel}")
            continue
        data = path.read_bytes()
        found.extend(f"비밀 값으로 보이는 내용: {rel}" for pattern in SECRETS if pattern.search(data))
    return found


def export(target, root=ROOT):
    target = Path(target).resolve()
    target.mkdir(parents=True, exist_ok=True)
    for old in target.iterdir():
        if old.name != ".git":
            shutil.rmtree(old) if old.is_dir() else old.unlink()
    for source, rel in server_files(root):
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target / rel)
    for source, name in EXTRAS.items():
        data = (root / source).read_bytes().replace(b"\r\n", b"\n")   # Linux 서버에서 쓰는 파일
        (target / name).write_bytes(data)
    return problems(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="배포용 저장소 폴더")
    found = export(parser.parse_args().target)
    for line in found:
        print(line)
    if found:
        return 1
    print("복사 완료. 내용을 확인한 뒤 배포용 저장소에서 커밋하고 푸시해 주세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
