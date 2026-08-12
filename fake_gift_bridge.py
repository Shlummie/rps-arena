import argparse
import json
import random
import time
import urllib.error
import urllib.request


TEAMS = ("rock", "paper", "scissors")
TIERS = ("small", "medium", "large")


def post_event(url, event):
    data = json.dumps(event).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.read().decode("utf-8")


def build_event(args):
    team = args.team if args.team != "random" else random.choice(TEAMS)
    tier = args.tier if args.tier != "random" else random.choice(TIERS)
    coins = args.coins
    if coins is None:
        coins = {"small": 1, "medium": 99, "large": 1000}[tier]
    return {
        "type": "gift",
        "team": team,
        "tier": tier,
        "user": args.user,
        "gift_name": args.gift,
        "coins": coins,
    }


def main():
    parser = argparse.ArgumentParser(description="Send local gift-shaped test events to the RPS stream game.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--team", choices=TEAMS + ("random",), default="random")
    parser.add_argument("--tier", choices=TIERS + ("random",), default="small")
    parser.add_argument("--user", default="test_viewer")
    parser.add_argument("--gift", default="Test Gift")
    parser.add_argument("--coins", type=int)
    parser.add_argument("--burst", type=int, default=1, help="Send this many events.")
    parser.add_argument("--delay", type=float, default=0.35, help="Delay between burst events.")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/event"
    for index in range(max(1, args.burst)):
        event = build_event(args)
        if args.burst > 1:
            event["user"] = f"{args.user}_{index + 1}"
        try:
            print(post_event(url, event))
        except urllib.error.URLError as exc:
            raise SystemExit(f"Could not reach {url}: {exc}") from exc
        if index + 1 < args.burst:
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
