# Briefly — Backend Pipeline

Runs every weekday at 7am ET. Pulls users from Supabase, fetches news, writes AI summaries, sends personalized emails.

## Deploy to Railway (free)

1. Go to railway.app and sign up free
2. Click "New Project" → "Deploy from GitHub repo"
3. Push this folder to a GitHub repo called `briefly-backend`
4. Connect that repo to Railway

## Set environment variables in Railway

In your Railway project → Variables tab, add these:

```
SUPABASE_URL=https://zesuoeedskxmrtfvpigc.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inplc3VvZWVkc2t4bXJ0ZnZwaWdjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODAxNjU1MjIsImV4cCI6MjA5NTc0MTUyMn0.p6UHsDoIVA6jvXct0VdfbHSxf09JQ-Gj-z-22LMMzRY
NEWSAPI_KEY=2b062d1b24ef437091c6a9e86caff5d6
RESEND_KEY=re_HKhjQRh6_5r8AAuvb52ssWzmKaDdZvdPy
ANTHROPIC_KEY=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
FROM_EMAIL=Briefly <onboarding@resend.dev>
```

## Schedule

The pipeline runs Mon–Fri at 11am UTC (7am ET).
To change the time, edit `cronSchedule` in `railway.toml`.

## How it works

1. Pulls all rows from your Supabase `signups` table
2. For each user, searches NewsAPI using their topics + custom tracking terms
3. Sends each article title + description to Claude Haiku for a "why it matters" sentence
4. Builds a personalized HTML email
5. Sends via Resend

## To test locally

```bash
pip install -r requirements.txt
export SUPABASE_URL=...  (paste each variable)
python main.py
```
