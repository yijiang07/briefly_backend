import os
import re
import time
import requests
from datetime import datetime, timedelta
from supabase import create_client

# ── KEYS ──
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
NEWSAPI_KEY  = os.environ.get("NEWSAPI_KEY")
RESEND_KEY   = os.environ.get("RESEND_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY")
FROM_EMAIL   = os.environ.get("FROM_EMAIL", "Briefly <onboarding@resend.dev>")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── LOW-QUALITY SOURCE BLOCKLIST ──
BLOCKED_SOURCES = {
    "youtube.com", "reddit.com", "pinterest.com",
    "facebook.com", "twitter.com", "x.com", "tiktok.com",
}

# ── TOPIC → SEARCH TERM MAPPING ──
TOPIC_MAP = {
    "AI & ML":              ["artificial intelligence", "machine learning", "large language model"],
    "Startups":             ["startup", "founder", "early stage"],
    "Venture capital":      ["venture capital", "series A", "funding round"],
    "Finance & macro":      ["federal reserve", "inflation", "interest rates", "economy"],
    "Tech industry":        ["technology", "big tech", "software"],
    "Climate & energy":     ["climate change", "renewable energy", "clean energy"],
    "Biotech & health":     ["biotech", "pharmaceutical", "clinical trial", "healthcare"],
    "Policy & regulation":  ["regulation", "legislation", "policy", "government"],
    "Crypto & web3":        ["cryptocurrency", "bitcoin", "blockchain", "web3"],
    "Product & design":     ["product design", "UX", "user experience"],
    "Space & science":      ["space exploration", "NASA", "scientific research"],
    "Career & hiring":      ["hiring", "layoffs", "job market", "remote work"],
    "Research & academia":  ["research paper", "university", "academic study"],
    "Sports":               ["sports", "championship", "athlete"],
    "Local news":           ["local news", "community"],
    "World affairs":        ["international", "geopolitics", "foreign policy"],
}


# ── STEP 1: GET ALL USERS ──
def get_users():
    result = supabase.table("signups").select("*").execute()
    return result.data


# ── STEP 2: FETCH NEWS (one call per topic, then merge + score) ──
def fetch_articles(topics: str, custom_tracking: str):
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Build per-topic queries
    topic_list = [t.strip() for t in topics.split(",") if t.strip()] if topics else []
    custom_list = [t.strip() for t in custom_tracking.split(",") if t.strip()
                   and t.strip().upper() != "EMPTY"] if custom_tracking else []

    all_terms = []  # (search_query, weight) — custom terms get higher weight
    for topic in topic_list:
        mapped = TOPIC_MAP.get(topic, [topic.lower()])
        all_terms.append((mapped[0], 1))          # primary mapped term
    for custom in custom_list:
        all_terms.append((custom, 2))             # custom terms weighted higher

    if not all_terms:
        all_terms = [("technology startups", 1)]

    # Fetch per-term, deduplicate across calls
    seen_titles = set()
    raw_articles = []

    for query, weight in all_terms[:6]:           # cap at 6 API calls
        try:
            res = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "from": yesterday,
                    "sortBy": "relevancy",
                    "language": "en",
                    "pageSize": 10,
                    "apiKey": NEWSAPI_KEY,
                },
                timeout=10,
            )
            data = res.json()
            if data.get("status") != "ok":
                print(f"  NewsAPI error for '{query}': {data.get('message','')}")
                continue

            for a in data.get("articles", []):
                title = a.get("title", "")
                desc  = a.get("description", "")
                url   = a.get("url", "")
                source_name = a.get("source", {}).get("name", "")

                # Filter junk
                if not title or not desc:
                    continue
                if title in ("[Removed]", ""):
                    continue
                if any(blocked in url for blocked in BLOCKED_SOURCES):
                    continue
                # Filter articles older than 48 hours
                published = a.get("publishedAt", "")
                if published:
                    try:
                        pub_dt = datetime.strptime(published[:19], "%Y-%m-%dT%H:%M:%S")
                        if (datetime.utcnow() - pub_dt).total_seconds() > 172800:
                            continue
                    except Exception:
                        pass

                if title not in seen_titles:
                    seen_titles.add(title)
                    a["_weight"] = weight
                    raw_articles.append(a)

            time.sleep(0.2)   # be polite to the API

        except Exception as e:
            print(f"  NewsAPI error for '{query}': {e}")
            continue

    if not raw_articles:
        print("  No raw articles collected.")
        return []

    # Score each article by relevance to user's full interest set
    all_user_terms = (
        [t.lower() for t in topic_list] +
        [v.lower() for topic in topic_list for v in TOPIC_MAP.get(topic, [])] +
        [c.lower() for c in custom_list]
    )

    def score(article):
        text = (article.get("title", "") + " " + article.get("description", "")).lower()
        term_hits = sum(1 for term in all_user_terms if term in text)
        return term_hits * article.get("_weight", 1)

    raw_articles.sort(key=score, reverse=True)
    print(f"  {len(raw_articles)} unique articles collected, returning top 5.")
    return raw_articles[:5]


# ── STEP 3: GENERATE DAY SUMMARY ──
def get_day_summary(articles: list, user_topics: str):
    headlines = "\n".join(
        f"- {a.get('title','')} ({a.get('source',{}).get('name','')})"
        for a in articles
    )
    prompt = f"""You are writing a 2-3 sentence intro paragraph for a personalized news briefing email.

The reader follows: {user_topics}

Today's top stories:
{headlines}

Write a punchy, intelligent 2-3 sentence paragraph summarizing the overall news theme for today as it relates to the reader's interests. 
- Be specific, not generic
- Mention 1-2 concrete story details
- Sound like a smart analyst, not a robot
- Do NOT start with "Today" or "Here are"
- Max 60 words"""

    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 150,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15,
        )
        data = res.json()
        return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"  Claude day summary error: {e}")
        return ""


# ── STEP 4: AI WHY IT MATTERS FOR EACH ARTICLE ──
def get_why_it_matters(article: dict, user_topics: str):
    prompt = f"""You are writing one sentence for a personalized news briefing.

The reader follows these topics: {user_topics}

Article: {article['title']}
Description: {article.get('description', '')}

Write ONE sentence starting with "Why it matters:" that explains why this story is relevant to someone following those topics. Be specific and direct. Max 30 words."""

    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15,
        )
        data = res.json()
        return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"  Claude error: {e}")
        return "Why it matters: This story is relevant to your tracked topics."


# ── STEP 5: BUILD EMAIL HTML ──
def build_email(user: dict, articles: list, day_summary: str):
    today = datetime.utcnow().strftime("%A, %B %-d")
    topics_display = user.get("topics", "your topics")

    # Day summary block
    summary_html = ""
    if day_summary:
        summary_html = f"""
    <div style="background:#eef1ff;border-left:3px solid #2b4fff;border-radius:0 10px 10px 0;padding:14px 18px;margin-bottom:24px;">
      <div style="font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:#2b4fff;margin-bottom:6px;">Today's Overview</div>
      <div style="font-size:14px;color:#0f0e0c;line-height:1.7;">{day_summary}</div>
    </div>"""

    stories_html = ""
    for a in articles:
        source = a.get("source", {}).get("name", "")
        title  = a.get("title", "")
        url    = a.get("url", "#")
        why    = a.get("why_it_matters", "")

        stories_html += f"""
        <div style="padding:18px 0;border-bottom:1px solid #e8e4dc;">
          <div style="font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:#2b4fff;margin-bottom:6px;">{source}</div>
          <div style="font-family:Georgia,serif;font-size:17px;font-weight:400;margin-bottom:7px;line-height:1.4;">
            <a href="{url}" style="color:#0f0e0c;text-decoration:none;">{title}</a>
          </div>
          <div style="font-size:13px;color:#7a7670;line-height:1.6;">{why}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f2eb;font-family:'DM Sans',Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:32px 16px;">

    <!-- Header -->
    <div style="border-bottom:1px solid #e8e4dc;padding-bottom:20px;margin-bottom:24px;">
      <div style="font-family:Georgia,serif;font-size:22px;font-weight:400;margin-bottom:4px;">● Briefly</div>
      <div style="font-size:12px;color:#7a7670;">{today} · personalized to your interests</div>
    </div>

    <!-- Intro -->
    <div style="font-size:14px;color:#7a7670;margin-bottom:16px;line-height:1.6;">
      Here's what matters today across <strong style="color:#0f0e0c;">{topics_display}</strong>.
    </div>

    <!-- Day Summary -->
    {summary_html}

    <!-- Stories -->
    <div style="background:#fff;border-radius:16px;padding:8px 24px 8px;border:1px solid #e8e4dc;">
      {stories_html}
    </div>

    <!-- Feedback -->
    <div style="margin-top:24px;padding:18px;background:#ede9df;border-radius:12px;text-align:center;">
      <div style="font-size:12px;color:#7a7670;margin-bottom:10px;">How was today's brief?</div>
      <a href="mailto:hello@readbriefly.com?subject=👍 Good brief" style="display:inline-block;margin:0 6px;padding:7px 16px;background:#fff;border-radius:100px;font-size:12px;color:#0f0e0c;text-decoration:none;border:1px solid #e8e4dc;">👍 Good</a>
      <a href="mailto:hello@readbriefly.com?subject=👎 Not quite" style="display:inline-block;margin:0 6px;padding:7px 16px;background:#fff;border-radius:100px;font-size:12px;color:#0f0e0c;text-decoration:none;border:1px solid #e8e4dc;">👎 Not quite</a>
      <a href="mailto:hello@readbriefly.com?subject=✏️ Missing topics" style="display:inline-block;margin:0 6px;padding:7px 16px;background:#fff;border-radius:100px;font-size:12px;color:#0f0e0c;text-decoration:none;border:1px solid #e8e4dc;">✏️ Wrong topics</a>
    </div>

    <!-- Footer -->
    <div style="margin-top:24px;text-align:center;font-size:11px;color:#7a7670;line-height:1.8;">
      You're receiving this because you signed up at readbriefly.com<br>
      <a href="#" style="color:#7a7670;">Unsubscribe</a> · <a href="#" style="color:#7a7670;">Update preferences</a>
    </div>

  </div>
</body>
</html>"""


# ── STEP 6: SEND EMAIL ──
def send_email(to_email: str, subject: str, html: str):
    try:
        res = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        if res.status_code == 200:
            print(f"  ✓ Sent to {to_email}")
        else:
            print(f"  ✗ Failed to send to {to_email}: {res.text}")
    except Exception as e:
        print(f"  Resend error for {to_email}: {e}")


# ── MAIN PIPELINE ──
def run():
    print(f"\n🗞  Briefly pipeline starting — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    users = get_users()
    print(f"→ {len(users)} users found")

    if not users:
        print("No users yet. Exiting.")
        return

    today = datetime.utcnow().strftime("%A, %B %-d")

    for user in users:
        email  = user.get("email")
        topics = user.get("topics", "")
        custom = user.get("custom_tracking", "")

        print(f"\nProcessing {email}...")

        # Fetch news
        articles = fetch_articles(topics, custom)
        if not articles:
            print(f"  No articles found for {email}, skipping.")
            continue

        user_topics = f"{topics}, {custom}".strip(", ")

        # Generate day summary
        print("  Generating day summary...")
        day_summary = get_day_summary(articles, user_topics)

        # Get why it matters for each article
        for article in articles:
            article["why_it_matters"] = get_why_it_matters(article, user_topics)

        # Build and send
        html = build_email(user, articles, day_summary)
        subject = f"Your Briefly for {today}"
        send_email(email, subject, html)

    print("\n✓ Pipeline complete.")


if __name__ == "__main__":
    run()
