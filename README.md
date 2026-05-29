# Domain Tree

A tiny Times New Roman web app for finding available brand domains from concept territories.

It uses:

- OpenAI embeddings for semantic expansion
- WhoisXMLAPI Domain Availability API for real availability checks
- Flask as a Python Vercel Function
- `.com` by default
- optional `.io`
- optional `studio / labs / works / systems / tools` variants

## Files

```txt
app.py
requirements.txt
vercel.json
templates/index.html
.env.example
.gitignore
README.md
```

## Deploy to Vercel

1. Create a GitHub repo.
2. Upload all files from this folder.
3. Import the repo into Vercel.
4. Add these environment variables in Vercel:

```txt
OPENAI_API_KEY
OPENAI_EMBEDDING_MODEL
WHOISXMLAPI_KEY
MAX_CHECKS_HARD_LIMIT
DOMAIN_CHECK_SLEEP
```

Suggested values:

```txt
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
MAX_CHECKS_HARD_LIMIT=120
DOMAIN_CHECK_SLEEP=0.05
```

5. Deploy.

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For local development, either export your env vars manually:

```bash
export OPENAI_API_KEY="..."
export WHOISXMLAPI_KEY="..."
python app.py
```

or install python-dotenv and load a local `.env` yourself.

Then open:

```txt
http://127.0.0.1:5050
```

## Important notes

Keep max checks low at first. Domain availability APIs often charge per lookup.

The app only shows available domains unless you toggle "show taken/unknown too."
