import os
import re
import base64
import time
import requests
import feedparser
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from supabase import create_client

# ── KEYS ──
SUPABASE_URL  = os.environ.get("SUPABASE_URL")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY")
RESEND_KEY    = os.environ.get("RESEND_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY")
FROM_EMAIL    = os.environ.get("FROM_EMAIL", "Briefly <onboarding@resend.dev>")
SITE_URL      = os.environ.get("SITE_URL", "https://www.readbriefly.com")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── LOGO ──
LOGO_SVG = '●'

# ── RSS FEEDS BY TOPIC ──
RSS_FEEDS = {
    "AI & ML": [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "https://www.technologyreview.com/feed/",
        "https://venturebeat.com/category/ai/feed/",
        "https://www.wired.com/feed/category/artificial-intelligence/latest/rss",
    ],
    "Startups": [
        "https://techcrunch.com/category/startups/feed/",
        "https://venturebeat.com/category/entrepreneur/feed/",
        "https://www.wired.com/feed/category/business/latest/rss",
        "https://feeds.feedburner.com/entrepreneur/latest",
    ],
    "Venture capital": [
        "https://techcrunch.com/category/venture/feed/",
        "https://news.crunchbase.com/feed/",
        "https://strictlyvc.com/feed/",
    ],
    "Finance & macro": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://www.ft.com/rss/home",
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://fortune.com/feed/",
    ],
    "Tech industry": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://arstechnica.com/feed/",
        "https://www.wired.com/feed/rss",
        "https://feeds.feedburner.com/venturebeat/SZYF",
    ],
    "Climate & energy": [
        "https://feeds.reuters.com/reuters/environment",
        "https://insideclimatenews.org/feed/",
        "https://www.theguardian.com/environment/rss",
        "https://www.bbc.co.uk/news/science_and_environment/rss.xml",
        "https://e360.yale.edu/feed",
    ],
    "Biotech & health": [
        "https://www.statnews.com/feed/",
        "https://feeds.reuters.com/reuters/healthNews",
        "https://www.fiercebiotech.com/rss/xml",
        "https://www.nature.com/nature.rss",
        "https://www.sciencedaily.com/rss/health_medicine.xml",
    ],
    "Policy & regulation": [
        "https://feeds.reuters.com/Reuters/PoliticsNews",
        "https://rss.politico.com/politics-news.xml",
        "https://thehill.com/feed/",
        "https://www.theguardian.com/politics/rss",
    ],
    "Crypto & web3": [
        "https://cointelegraph.com/rss",
        "https://coindesk.com/arc/outboundfeeds/rss/",
        "https://decrypt.co/feed",
        "https://techcrunch.com/category/cryptocurrency/feed/",
    ],
    "Product & design": [
        "https://www.producthunt.com/feed",
        "https://uxdesign.cc/feed",
        "https://www.smashingmagazine.com/feed/",
        "https://feeds.feedburner.com/alistapart/main",
    ],
    "Space & science": [
        "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "https://www.sciencedaily.com/rss/space_time.xml",
        "https://www.space.com/feeds/all",
        "https://www.newscientist.com/feed/home/",
        "https://feeds.reuters.com/reuters/scienceNews",
    ],
    "Career & hiring": [
        "https://hbr.org/resources/rss/hbr-rss-feeds.xml",
        "https://feeds.feedburner.com/FastCompany",
        "https://www.theladders.com/rss/career-advice.rss",
    ],
    "Research & academia": [
        "https://www.nature.com/nature.rss",
        "https://www.sciencedaily.com/rss/all.xml",
        "https://news.mit.edu/rss/research",
        "https://phys.org/rss-feed/",
    ],
    "Sports": [
        "https://feeds.bbci.co.uk/sport/rss.xml",
        "https://www.espn.com/espn/rss/news",
        "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",
        "https://sports.yahoo.com/rss/",
    ],
    "Local news": [
        "https://feeds.reuters.com/Reuters/domesticNews",
        "https://rss.nytimes.com/services/xml/rss/nyt/US.xml",
        "https://feeds.npr.org/1003/rss.xml",
    ],
    "World affairs": [
        "https://feeds.reuters.com/Reuters/worldNews",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.theguardian.com/world/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://feeds.npr.org/1004/rss.xml",
        "https://foreignpolicy.com/feed/",
    ],
}

# General high-quality feeds for custom tracking terms
GENERAL_FEEDS = [
    "https://feeds.reuters.com/reuters/topNews",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://feeds.npr.org/1001/rss.xml",
    "https://www.theguardian.com/world/rss",
    "https://techcrunch.com/feed/",
    "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    "https://www.ft.com/rss/home",
    "https://feeds.bloomberg.com/technology/news.rss",
    "https://arstechnica.com/feed/",
]


# ── HELPERS ──
def make_unsub_token(email: str) -> str:
    return base64.urlsafe_b64encode(email.encode()).decode()

def make_unsub_link(email: str) -> str:
    return f"{SITE_URL}/unsubscribe.html?token={make_unsub_token(email)}"

def parse_date(entry) -> datetime:
    """Parse published date from RSS entry, return UTC datetime."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                import calendar
                return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)

def fetch_feed(url: str, timeout: int = 8):
    """Fetch and parse a single RSS feed, return list of entries."""
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Briefly/1.0"})
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.content)
        return feed.entries or []
    except Exception:
        return []

def entry_to_article(entry, source_name: str) -> dict:
    """Convert feedparser entry to article dict."""
    title = entry.get("title", "").strip()
    # Strip HTML from description
    desc  = re.sub(r"<[^>]+>", "", entry.get("summary", entry.get("description", ""))).strip()
    url   = entry.get("link", "")
    return {
        "title":       title,
        "description": desc[:300] if desc else "",
        "url":         url,
        "source":      {"name": source_name},
        "publishedAt": parse_date(entry).isoformat(),
        "_pub_dt":     parse_date(entry),
    }


# ── STEP 1: GET ACTIVE USERS ──
def get_users():
    result = (
        supabase.table("signups")
        .select("*")
        .neq("unsubscribed", True)
        .execute()
    )
    return result.data


# ── STEP 2: FETCH NEWS FROM RSS ──
def fetch_articles(topics: str, custom_tracking: str):
    cutoff      = datetime.now(timezone.utc) - timedelta(hours=48)
    topic_list  = [t.strip() for t in topics.split(",")          if t.strip()] if topics else []
    custom_list = [t.strip() for t in custom_tracking.split(",") if t.strip() and t.strip().upper() != "EMPTY"] if custom_tracking else []

    seen, raw = set(), []

    # Fetch topic-specific feeds
    feeds_to_fetch = []
    for topic in topic_list:
        for feed_url in RSS_FEEDS.get(topic, []):
            feeds_to_fetch.append((feed_url, topic, 1))

    # For custom terms, pull from general feeds
    for feed_url in GENERAL_FEEDS:
        feeds_to_fetch.append((feed_url, "general", 1))

    # Deduplicate feed URLs, keep topic association
    seen_urls = set()
    unique_feeds = []
    for feed_url, topic, weight in feeds_to_fetch:
        if feed_url not in seen_urls:
            seen_urls.add(feed_url)
            unique_feeds.append((feed_url, topic, weight))

    print(f"  Fetching {len(unique_feeds)} RSS feeds...")

    for feed_url, topic, weight in unique_feeds:
        source_name = feed_url.split("/")[2].replace("www.", "").replace("feeds.", "").split(".")[0].title()
        entries = fetch_feed(feed_url)
        for entry in entries:
            article = entry_to_article(entry, source_name)
            title   = article["title"]
            if not title or not article["description"]:
                continue
            if title in seen:
                continue
            # Filter old articles
            if article["_pub_dt"] < cutoff:
                continue
            seen.add(title)
            article["_weight"] = weight
            article["_topic"]  = topic
            raw.append(article)
        time.sleep(0.05)

    if not raw:
        print("  No articles from RSS feeds.")
        return []

    # Score by relevance to user's interests
    all_terms = (
        [t.lower() for t in topic_list] +
        [t.lower().replace(" & ", " ").replace("&", "") for t in topic_list] +
        [c.lower() for c in custom_list]
    )

    def score(a):
        text       = (a.get("title", "") + " " + a.get("description", "")).lower()
        term_hits  = sum(1 for term in all_terms if term and term in text)
        # Boost custom tracking matches
        custom_hits = sum(2 for c in custom_list if c.lower() in text)
        # Recency boost: articles from last 12h get +1
        age_hours  = (datetime.now(timezone.utc) - a["_pub_dt"]).total_seconds() / 3600
        recency    = 1 if age_hours < 12 else 0
        return term_hits + custom_hits + recency

    raw.sort(key=score, reverse=True)
    print(f"  {len(raw)} total articles, returning top 5.")
    return raw[:5]


# ── STEP 3: AI WHY IT MATTERS ──
def get_why_it_matters(article: dict, user_topics: str):
    prompt = f"""Write ONE sentence starting with "Why it matters:" explaining why this is relevant to someone following: {user_topics}

Article: {article['title']}
Description: {article.get('description', '')}

Be specific and direct. Max 30 words."""
    try:
        res = requests.post(
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
      Every morning, Briefly scans dozens of top sources and builds a personalized briefing based on what you care about.
      No noise, no algorithm — just the stories that matter to you, with a plain-English explanation of why each one is relevant.
    </div>
    <div style="background:#fff;border-radius:16px;padding:24px;border:1px solid #e8e4dc;margin-bottom:28px;">
      <div style="font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:#2b4fff;margin-bottom:10px;">Your topics</div>
      <div style="font-size:15px;color:#0f0e0c;line-height:1.7;">{topics_display}</div>
    </div>
    <div style="background:#eef1ff;border-left:3px solid #2b4fff;border-radius:0 10px 10px 0;padding:14px 18px;margin-bottom:28px;">
      <div style="font-size:13px;color:#0f0e0c;line-height:1.7;">
        <strong>Want to change your topics?</strong> Just reply to this email and let us know.
      </div>
    </div>
    <div style="font-size:14px;color:#7a7670;line-height:1.7;margin-bottom:28px;">
      Talk soon,<br><strong style="color:#0f0e0c;">The Briefly team</strong>
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
            json={"from": FROM_EMAIL, "to": [email],
                  "subject": "Welcome to Briefly — your first brief arrives tomorrow",
                  "html": html, "tags": [{"name": "type", "value": "welcome"}]},
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
    if not today:
        tz_name = user.get("timezone") or "America/New_York"
        try:
            today = datetime.now(ZoneInfo(tz_name)).strftime("%A, %B %-d")
        except Exception:
            today = datetime.now(ZoneInfo("America/New_York")).strftime("%A, %B %-d")

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
            json={"from": FROM_EMAIL, "to": [to_email], "subject": subject, "html": html,
                  "tags": [{"name": "type", "value": "daily_brief"}]},
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
        print(f"Welcome step skipped: {e}")

    # Send daily briefs
    users = get_users()
    print(f"\n→ {len(users)} active users")
    if not users:
        print("No users. Exiting.")
        return

    for user in users:
        email  = user.get("email")
        topics = user.get("topics", "")
        custom = user.get("custom_tracking", "")
        print(f"\nProcessing {email}...")

        # Compute date in user's timezone
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

        html = build_email(user, articles, today)
        send_email(email, f"Your Briefly for {today}", html)

    print("\n✓ Pipeline complete.")


if __name__ == "__main__":
    run()
