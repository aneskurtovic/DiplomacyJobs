"""Read a public Telegram channel's web preview (t.me/s/CHANNEL): channel info and keyword searches.

The preview is Telegram's public, no-login HTML view of a channel. Used to check whether a
mission announces vacancies there.

Usage:
  python scripts/telegram_probe.py CHANNEL [--q WORD ...] [--before ID]
"""
import argparse
import ssl
import sys

import httpx
from bs4 import BeautifulSoup


def messages(soup):
    for message in soup.select(".tgme_widget_message[data-post]"):
        text = message.select_one(".tgme_widget_message_text")
        stamp = message.select_one("time[datetime]")
        yield message["data-post"], stamp["datetime"] if stamp else "", text.get_text(" ", strip=True) if text else ""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("channel")
    parser.add_argument("--q", nargs="*", default=[])
    parser.add_argument("--before", default="")
    parser.add_argument("--chars", type=int, default=300)
    args = parser.parse_args()
    url = f"https://t.me/s/{args.channel}"
    with httpx.Client(timeout=25, follow_redirects=True, verify=ssl.create_default_context(), headers={"User-Agent": "Mozilla/5.0 (compatible; DiplomacyJobsBot/1.0)"}) as client:
        page = client.get(url, params={"before": args.before} if args.before else None)
        soup = BeautifulSoup(page.text, "html.parser")
        title = soup.select_one(".tgme_channel_info_header_title")
        description = soup.select_one(".tgme_channel_info_description")
        counters = [c.get_text(" ", strip=True) for c in soup.select(".tgme_channel_info_counter")]
        print(f"HTTP {page.status_code} {page.url}")
        print("title:", title.get_text(" ", strip=True) if title else None)
        print("description:", description.get_text(" ", strip=True) if description else None)
        print("links:", [a["href"] for a in description.select("a[href]")] if description else [])
        print("counters:", counters)
        posts = list(messages(soup))
        if posts:
            print(f"page: {len(posts)} posts, {posts[0][1]} .. {posts[-1][1]}")
        for post, stamp, text in posts if not args.q else []:
            print(f"  {stamp} {post}: {text[:args.chars]}")
        for word in args.q:
            soup = BeautifulSoup(client.get(url, params={"q": word}).text, "html.parser")
            hits = list(messages(soup))
            print(f"q={word!r}: {len(hits)} hits")
            for post, stamp, text in hits:
                print(f"  {stamp} {post}: {text[:args.chars]}")


if __name__ == "__main__":
    main()
