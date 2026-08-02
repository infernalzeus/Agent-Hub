# YouTube credentials (not committed)

The upload feature needs a Google OAuth client and a per-account token. **Neither is
included in this repo** — they are ignored by `.gitignore`. Create your own:

```
youtube/credentials/
└── <ACCOUNT_TAG>/            # e.g. "IZ17-G" — must match the key in hub/config.py YOUTUBE_ACCOUNTS
    ├── client_secrets.json   # you provide (see below)
    └── youtube_token.pickle  # auto-created on first upload after you authorize
```

## 1. Get `client_secrets.json`

1. In the [Google Cloud Console](https://console.cloud.google.com/) create (or reuse) a project.
2. Enable the **YouTube Data API v3**.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID → Desktop app**.
4. Download the JSON, rename it to `client_secrets.json`, and drop it in
   `youtube/credentials/<ACCOUNT_TAG>/`.

## 2. Register the account in config

Add an entry to `YOUTUBE_ACCOUNTS` in [`hub/config.py`](../../hub/config.py) whose key is your
`<ACCOUNT_TAG>`, pointing at the two files above.

## 3. First run

The first upload opens a browser consent screen. After you approve, the refresh token is
saved to `youtube_token.pickle` and reused thereafter. **That pickle grants control of your
YouTube account — keep it private; it is gitignored for a reason.**
