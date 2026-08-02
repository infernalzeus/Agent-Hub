"""
Agent CORE — standalone YouTube uploader.

Accepts an arbitrary video path + explicit credential paths so credentials
never need to live inside any project repo.

Usage:
  python yt_upload.py
    --video-path  /path/to/video.mp4
    --title       "My Video Title"
    --privacy     public
    --secrets-file  credentials/IZ17-G/client_secrets.json
    --token-file    credentials/IZ17-G/youtube_token.pickle
    [--description "..."]
    [--tags "tag1,tag2,tag3"]
    [--thumbnail   /path/to/thumb.png]
"""
from __future__ import annotations
import argparse
import os
import pickle
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _get_youtube_client(secrets_file: str, token_file: str):
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    creds  = None

    if os.path.exists(token_file):
        with open(token_file, "rb") as fh:
            creds = pickle.load(fh)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing Google token...")
            sys.stdout.flush()
            creds.refresh(Request())
            print("Token refreshed.")
        else:
            if not os.path.exists(secrets_file):
                sys.exit(
                    f"ERROR: client_secrets.json not found at: {secrets_file}\n"
                    "Place the Google OAuth Desktop JSON there and retry."
                )
            print("Google auth required — browser opening for one-time login...")
            sys.stdout.flush()
            flow  = InstalledAppFlow.from_client_secrets_file(secrets_file, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)
            print("Auth complete.")

        os.makedirs(os.path.dirname(os.path.abspath(token_file)), exist_ok=True)
        with open(token_file, "wb") as fh:
            pickle.dump(creds, fh)

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
    secrets_file: str,
    token_file: str,
    thumbnail: str | None = None,
) -> str:
    from googleapiclient.http import MediaFileUpload

    youtube = _get_youtube_client(secrets_file, token_file)

    body = {
        "snippet": {
            "title":           title[:100],
            "description":     description[:5000],
            "tags":            tags,
            "categoryId":      "24",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus":           privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    size_mb = os.path.getsize(video_path) / 1_048_576
    print(f"Uploading  {os.path.basename(video_path)}  ({size_mb:.1f} MB)  →  {privacy}")
    sys.stdout.flush()

    media = MediaFileUpload(
        video_path, mimetype="video/mp4", resumable=True, chunksize=4 * 1_048_576
    )
    req         = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response    = None
    retry_delay = 10
    MAX_RETRIES = 5

    while response is None:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                status, response = req.next_chunk()
                break
            except Exception as exc:
                if attempt == MAX_RETRIES:
                    raise
                print(f"  Chunk failed (attempt {attempt}/{MAX_RETRIES}): {exc}")
                print(f"  Retrying in {retry_delay}s...")
                sys.stdout.flush()
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
        if status:
            print(f"  Progress: {int(status.progress() * 100):3d}%")
            sys.stdout.flush()

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"Upload complete! {url}")
    sys.stdout.flush()

    if thumbnail and os.path.exists(thumbnail):
        print("Setting thumbnail...")
        sys.stdout.flush()
        mime = "image/png" if thumbnail.lower().endswith(".png") else "image/jpeg"
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail, mimetype=mime),
        ).execute()
        print("Thumbnail set.")
        sys.stdout.flush()

    return url


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent CORE — YouTube uploader")
    parser.add_argument("--video-path",   required=True)
    parser.add_argument("--title",        required=True)
    parser.add_argument("--description",  default="")
    parser.add_argument("--tags",         default="", help="Comma-separated")
    parser.add_argument("--privacy",      choices=["private", "unlisted", "public"],
                        default="private")
    parser.add_argument("--secrets-file", required=True)
    parser.add_argument("--token-file",   required=True)
    parser.add_argument("--thumbnail",    default="", help="Path to thumbnail image (PNG/JPG)")
    args = parser.parse_args()

    if not os.path.exists(args.video_path):
        sys.exit(f"ERROR: video not found: {args.video_path}")

    tags      = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    thumbnail = args.thumbnail if args.thumbnail and os.path.exists(args.thumbnail) else None
    upload_video(args.video_path, args.title, args.description, tags,
                 args.privacy, args.secrets_file, args.token_file, thumbnail)


if __name__ == "__main__":
    main()
