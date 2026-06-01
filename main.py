import os
import base64
import time
import requests
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from supabase import create_client

# ── KEYS ──
SUPABASE_URL  = os.environ.get("SUPABASE_URL")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY")
NEWSAPI_KEY   = os.environ.get("NEWSAPI_KEY")
RESEND_KEY    = os.environ.get("RESEND_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY")
FROM_EMAIL    = os.environ.get("FROM_EMAIL", "Briefly <onboarding@resend.dev>")
SITE_URL      = os.environ.get("SITE_URL", "https://www.readbriefly.com")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── LOGO ──
LOGO_SVG = ''

# ── TOPIC MAP ──
TOPIC_MAP = {
    "AI & ML":             "artificial intelligence",
    "Startups":            "startup",
    "Venture capital":     "venture capital",
    "Finance & macro":     "economy inflation",
    "Tech industry":       "technology",
    "Climate & energy":    "climate energy",
    "Biotech & health":    "biotech healthcare",
    "Policy & regulation": "regulation policy",
    "Crypto & web3":       "cryptocurrency blockchain",
    "Product & design":    "product design",
    "Space & science":     "space science",
    "Career & hiring":     "hiring jobs",
    "Research & academia": "research university",
    "Sports":              "sports",
    "Local news":          "local news",
    "World affairs":       "international geopolitics",
}

BLOCKED_SOURCES = {
    "youtube.com", "reddit.com", "pinterest.com",
    "facebook.com", "twitter.com", "x.com", "tiktok.com",
}


# ── HELPERS ──
def make_unsub_token(email: str) -> str:
    return base64.urlsafe_b64encode(email.encode()).decode()

def make_unsub_link(email: str) -> str:
    return f"{SITE_URL}/unsubscribe.html?token={make_unsub_token(email)}"


# ── STEP 1: GET ACTIVE USERS ──
def get_users():
    result = (
        supabase.table("signups")
        .select("*")
        .neq("unsubscribed", True)
        .execute()
    )
    return result.data


# ── STEP 2: FETCH NEWS ──
def fetch_articles(topics: str, custom_tracking: str):
    yesterday   = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    topic_list  = [t.strip() for t in topics.split(",")          if t.strip()] if topics else []
    custom_list = [t.strip() for t in custom_tracking.split(",") if t.strip() and t.strip().upper() != "EMPTY"] if custom_tracking else []

    queries = [(TOPIC_MAP.get(t, t.lower()), 1) for t in topic_list] + [(c, 2) for c in custom_list]
    if not queries:
        queries = [("technology startups", 1)]

    seen, raw = set(), []
    for query, weight in queries[:6]:
        try:
            res  = requests.get(
                "https://newsapi.org/v2/everything",
                params={"q": query, "from": yesterday, "sortBy": "relevancy",
                        "language": "en", "pageSize": 10, "apiKey": NEWSAPI_KEY},
                timeout=10,
            )
            data = res.json()
            if data.get("status") != "ok":
                print(f"  NewsAPI error for '{query}': {data.get('message','')}")
                continue
            for a in data.get("articles", []):
                title = a.get("title", "")
                url   = a.get("url", "")
                if not title or not a.get("description") or title == "[Removed]":
                    continue
                if any(b in url for b in BLOCKED_SOURCES):
                    continue
                pub = a.get("publishedAt", "")
                if pub:
                    try:
                        if (datetime.now(timezone.utc) - datetime.strptime(pub[:19], "%Y-%m-%dT%H:%M:%S")).total_seconds() > 172800:
                            continue
                    except Exception:
                        pass
                if title not in seen:
                    seen.add(title)
                    a["_weight"] = weight
                    raw.append(a)
            time.sleep(0.2)
        except Exception as e:
            print(f"  NewsAPI error for '{query}': {e}")

    if not raw:
        return []

    all_terms = (
        [t.lower() for t in topic_list] +
        [TOPIC_MAP.get(t, "").lower() for t in topic_list] +
        [c.lower() for c in custom_list]
    )

    def score(a):
        text = (a.get("title", "") + " " + a.get("description", "")).lower()
        return sum(1 for term in all_terms if term and term in text) * a.get("_weight", 1)

    raw.sort(key=score, reverse=True)
    print(f"  {len(raw)} articles collected, returning top 5.")
    return raw[:5]


# ── STEP 3: AI WHY IT MATTERS ──
def get_why_it_matters(article: dict, user_topics: str):
    prompt = f"""Write ONE sentence starting with "Why it matters:" explaining why this is relevant to someone following: {user_topics}

Article: {article['title']}
Description: {article.get('description', '')}

Be specific and direct. Max 30 words."""
    try:
        res  = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 100,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=15,
        )
        return res.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"  Claude error: {e}")
        return "Why it matters: This story is relevant to your tracked topics."


# ── STEP 4: WELCOME EMAIL ──
def send_welcome_email(email: str, topics: str):
    topics_display = topics or "your selected topics"
    unsub_link     = make_unsub_link(email)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f2eb;font-family:Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:32px 16px;">

    <div style="border-bottom:1px solid #e8e4dc;padding-bottom:20px;margin-bottom:28px;">
      <div style="font-family:Georgia,serif;font-size:22px;font-weight:400;margin-bottom:4px;">● Briefly</div>
      <div style="font-size:12px;color:#7a7670;">Welcome to your morning briefing</div>
    </div>

    <div style="font-family:Georgia,serif;font-size:24px;font-weight:400;margin-bottom:16px;line-height:1.3;">
      You're all set. Your first brief arrives tomorrow morning.
    </div>

    <div style="font-size:15px;color:#4a4845;line-height:1.7;margin-bottom:28px;">
      Every morning, Briefly scans 50+ sources and builds a personalized briefing based on what you care about.
      No noise, no algorithm — just the stories that matter to you, with a plain-English explanation of why each one is relevant.
    </div>

    <div style="background:#fff;border-radius:16px;padding:24px;border:1px solid #e8e4dc;margin-bottom:28px;">
      <div style="font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:#2b4fff;margin-bottom:10px;">Your topics</div>
      <div style="font-size:15px;color:#0f0e0c;line-height:1.7;">{topics_display}</div>
    </div>

    <div style="background:#eef1ff;border-left:3px solid #2b4fff;border-radius:0 10px 10px 0;padding:14px 18px;margin-bottom:28px;">
      <div style="font-size:13px;color:#0f0e0c;line-height:1.7;">
        <strong>Want to change your topics?</strong> Just reply to this email and let us know — we'll update them for you.
      </div>
    </div>

    <div style="font-size:14px;color:#7a7670;line-height:1.7;margin-bottom:28px;">
      Talk soon,<br>
      <strong style="color:#0f0e0c;">The Briefly team</strong>
    </div>

    <div style="border-top:1px solid #e8e4dc;padding-top:20px;text-align:center;font-size:11px;color:#7a7670;line-height:1.8;">
      You're receiving this because you signed up at readbriefly.com<br>
      <a href="{unsub_link}" style="color:#7a7670;text-decoration:underline;">Unsubscribe</a>
    </div>

  </div>
</body>
</html>"""

    try:
        res = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"},
            json={
                "from": FROM_EMAIL,
                "to": [email],
                "subject": "Welcome to Briefly — your first brief arrives tomorrow",
                "html": html,
                "tags": [{"name": "type", "value": "welcome"}],
            },
            timeout=15,
        )
        if res.status_code == 200:
            print(f"  ✓ Welcome email sent to {email}")
        else:
            print(f"  ✗ Welcome email failed: {res.text}")
    except Exception as e:
        print(f"  Welcome email error: {e}")


# ── STEP 5: BUILD DAILY EMAIL ──
def build_email(user: dict, articles: list, today: str = ""):
    topics_display = user.get("topics", "your topics")
    email          = user.get("email", "")
    unsub_link     = make_unsub_link(email)

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

    <div style="border-bottom:1px solid #e8e4dc;padding-bottom:20px;margin-bottom:24px;">
      <div style="font-family:Georgia,serif;font-size:22px;font-weight:400;margin-bottom:4px;">● Briefly</div>
      <div style="font-size:12px;color:#7a7670;">{today} · personalized to your interests</div>
    </div>

    <div style="font-size:14px;color:#7a7670;margin-bottom:24px;line-height:1.6;">
      Here's what matters today across <strong style="color:#0f0e0c;">{topics_display}</strong>.
    </div>

    <div style="background:#fff;border-radius:16px;padding:8px 24px;border:1px solid #e8e4dc;">
      {stories_html}
    </div>

    <div style="margin-top:24px;padding:18px;background:#ede9df;border-radius:12px;text-align:center;">
      <div style="font-size:12px;color:#7a7670;margin-bottom:10px;">How was today's brief?</div>
      <a href="mailto:hello@readbriefly.com?subject=👍 Good brief" style="display:inline-block;margin:0 6px;padding:7px 16px;background:#fff;border-radius:100px;font-size:12px;color:#0f0e0c;text-decoration:none;border:1px solid #e8e4dc;">👍 Good</a>
      <a href="mailto:hello@readbriefly.com?subject=👎 Not quite" style="display:inline-block;margin:0 6px;padding:7px 16px;background:#fff;border-radius:100px;font-size:12px;color:#0f0e0c;text-decoration:none;border:1px solid #e8e4dc;">👎 Not quite</a>
      <a href="mailto:hello@readbriefly.com?subject=✏️ Wrong topics" style="display:inline-block;margin:0 6px;padding:7px 16px;background:#fff;border-radius:100px;font-size:12px;color:#0f0e0c;text-decoration:none;border:1px solid #e8e4dc;">✏️ Wrong topics</a>
    </div>

    <div style="margin-top:24px;text-align:center;font-size:11px;color:#7a7670;line-height:1.8;">
      You're receiving this because you signed up at readbriefly.com<br>
      <a href="{unsub_link}" style="color:#7a7670;text-decoration:underline;">Unsubscribe</a>
    </div>

  </div>
</body>
</html>"""


# ── STEP 6: SEND EMAIL ──
def send_email(to_email: str, subject: str, html: str):
    try:
        res = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"},
            json={
                "from": FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "html": html,
                "tags": [{"name": "type", "value": "daily_brief"}],  # enables open tracking
            },
            timeout=15,
        )
        if res.status_code == 200:
            print(f"  ✓ Sent to {to_email}")
        else:
            print(f"  ✗ Failed {to_email}: {res.text}")
    except Exception as e:
        print(f"  Resend error: {e}")


# ── MAIN PIPELINE ──
def run():
    print(f"\n🗞  Briefly pipeline starting — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # Send welcome emails to new signups
    try:
        new_users = (
            supabase.table("signups")
            .select("*")
            .eq("welcome_sent", False)
            .neq("unsubscribed", True)
            .execute()
            .data
        )
        for u in new_users:
            print(f"\nSending welcome to {u['email']}...")
            send_welcome_email(u["email"], u.get("topics", ""))
            supabase.table("signups").update({"welcome_sent": True}).eq("email", u["email"]).execute()
    except Exception as e:
        print(f"Welcome step skipped (column may not exist yet): {e}")

    # Send daily briefs
    users = get_users()
    print(f"\n→ {len(users)} active users for daily brief")
    if not users:
        print("No users. Exiting.")
        return


    for user in users:
        email  = user.get("email")
        topics = user.get("topics", "")
        custom = user.get("custom_tracking", "")
        print(f"\nProcessing {email}...")

        # Compute today's date in user's timezone
        tz_name = user.get("timezone") or "America/New_York"
        try:
            user_tz = ZoneInfo(tz_name)
        except Exception:
            user_tz = ZoneInfo("America/New_York")
        today = datetime.now(user_tz).strftime("%A, %B %-d")

        articles = fetch_articles(topics, custom)
        if not articles:
            print(f"  No articles found, skipping.")
            continue

        user_topics = f"{topics}, {custom}".strip(", ")
        for article in articles:
            article["why_it_matters"] = get_why_it_matters(article, user_topics)

        html = build_email(user, articles)
        send_email(email, f"Your Briefly for {today}", html)

    print("\n✓ Pipeline complete.")


if __name__ == "__main__":
    run()
