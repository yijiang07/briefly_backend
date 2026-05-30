import os
import requests
from datetime import datetime, timedelta
from supabase import create_client

# ── KEYS ──
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")
RESEND_KEY = os.environ.get("RESEND_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "Briefly <onboarding@resend.dev>")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── STEP 1: GET ALL USERS ──
def get_users():
    result = supabase.table("signups").select("*").execute()
    return result.data


# ── STEP 2: FETCH NEWS FOR A USER ──
def fetch_articles(topics: str, custom_tracking: str):
    # Build a query from their topics + custom terms
    terms = []
    if topics:
        terms += [t.strip() for t in topics.split(",") if t.strip()]
    if custom_tracking:
        terms += [t.strip() for t in custom_tracking.split(",") if t.strip()]

    if not terms:
        terms = ["technology", "startups"]

    # Use the top 3 terms to keep the query focused
    query = " OR ".join(f'"{t}"' for t in terms[:3])

    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": yesterday,
        "sortBy": "relevancy",
        "language": "en",
        "pageSize": 10,
        "apiKey": NEWSAPI_KEY,
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        articles = data.get("articles", [])
        # Filter out articles with no description or title
        articles = [a for a in articles if a.get("title") and a.get("description")]
        # Deduplicate by title
        seen = set()
        unique = []
        for a in articles:
            if a["title"] not in seen:
                seen.add(a["title"])
                unique.append(a)
        return unique[:5]
    except Exception as e:
        print(f"NewsAPI error: {e}")
        return []


# ── STEP 3: AI SUMMARY FOR EACH ARTICLE ──
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
        print(f"Claude error: {e}")
        return "Why it matters: This story is relevant to your tracked topics."


# ── STEP 4: BUILD EMAIL HTML ──
def build_email(user: dict, articles: list):
    today = datetime.utcnow().strftime("%A, %B %-d")
    topics_display = user.get("topics", "your topics")

    stories_html = ""
    for a in articles:
        source = a.get("source", {}).get("name", "")
        title = a.get("title", "")
        url = a.get("url", "#")
        why = a.get("why_it_matters", "")

        stories_html += f"""
        <div style="padding:18px 0;border-bottom:1px solid #e8e4dc;">
          <div style="font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:#2b4fff;margin-bottom:6px;">{source}</div>
          <div style="font-family:Georgia,serif;font-size:17px;font-weight:400;margin-bottom:7px;line-height:1.4;">
            <a href="{url}" style="color:#0f0e0c;text-decoration:none;">{title}</a>
          </div>
          <div style="font-size:13px;color:#7a7670;line-height:1.6;">{why}</div>
        </div>
        """

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f2eb;font-family:'DM Sans',Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:32px 16px;">

    <!-- Header -->
    <div style="border-bottom:1px solid #e8e4dc;padding-bottom:20px;margin-bottom:24px;">
      <div style="font-family:Georgia,serif;font-size:22px;font-weight:400;margin-bottom:4px;">
        ● Briefly
      </div>
      <div style="font-size:12px;color:#7a7670;">{today} · personalized to your interests</div>
    </div>

    <!-- Intro -->
    <div style="font-size:14px;color:#7a7670;margin-bottom:24px;line-height:1.6;">
      Here's what matters today across <strong style="color:#0f0e0c;">{topics_display}</strong>.
    </div>

    <!-- Stories -->
    <div style="background:#fff;border-radius:16px;padding:8px 24px 8px;border:1px solid #e8e4dc;">
      {stories_html}
    </div>

    <!-- Feedback -->
    <div style="margin-top:24px;padding:18px;background:#ede9df;border-radius:12px;text-align:center;">
      <div style="font-size:12px;color:#7a7670;margin-bottom:10px;">How was today's brief?</div>
      <a href="mailto:feedback@getbriefly.com?subject=👍 Good brief" style="display:inline-block;margin:0 6px;padding:7px 16px;background:#fff;border-radius:100px;font-size:12px;color:#0f0e0c;text-decoration:none;border:1px solid #e8e4dc;">👍 Good</a>
      <a href="mailto:feedback@getbriefly.com?subject=👎 Not quite" style="display:inline-block;margin:0 6px;padding:7px 16px;background:#fff;border-radius:100px;font-size:12px;color:#0f0e0c;text-decoration:none;border:1px solid #e8e4dc;">👎 Not quite</a>
      <a href="mailto:feedback@getbriefly.com?subject=✏️ Missing topics" style="display:inline-block;margin:0 6px;padding:7px 16px;background:#fff;border-radius:100px;font-size:12px;color:#0f0e0c;text-decoration:none;border:1px solid #e8e4dc;">✏️ Wrong topics</a>
    </div>

    <!-- Footer -->
    <div style="margin-top:24px;text-align:center;font-size:11px;color:#7a7670;line-height:1.8;">
      You're receiving this because you signed up at getbriefly.com<br>
      <a href="#" style="color:#7a7670;">Unsubscribe</a> · <a href="#" style="color:#7a7670;">Update preferences</a>
    </div>

  </div>
</body>
</html>
"""


# ── STEP 5: SEND EMAIL ──
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
            print(f"✓ Sent to {to_email}")
        else:
            print(f"✗ Failed to send to {to_email}: {res.text}")
    except Exception as e:
        print(f"Resend error for {to_email}: {e}")


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
        email = user.get("email")
        topics = user.get("topics", "")
        custom = user.get("custom_tracking", "")

        print(f"\nProcessing {email}...")

        # Fetch news
        articles = fetch_articles(topics, custom)
        if not articles:
            print(f"  No articles found for {email}, skipping.")
            continue

        # Get AI summary for each article
        user_topics = f"{topics}, {custom}".strip(", ")
        for article in articles:
            article["why_it_matters"] = get_why_it_matters(article, user_topics)

        # Build and send email
        html = build_email(user, articles)
        subject = f"Your Briefly for {today}"
        send_email(email, subject, html)

    print("\n✓ Pipeline complete.")


if __name__ == "__main__":
    run()
