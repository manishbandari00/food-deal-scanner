"""
╔══════════════════════════════════════════════════════════╗
║           FOOD DATA ENGINE                              ║
║   Reads restaurants_data.json (base)                    ║
║   Randomizes prices, offers, status                     ║
║   Saves to live_data.json every 30 mins                 ║
║   Browser + Scanner both read live_data.json            ║
╚══════════════════════════════════════════════════════════╝

SETUP:
------
1. pip install rich schedule
2. Keep this file in same folder as restaurants_data.json
3. python data_engine.py
4. Keep it running in background!
"""

import json
import random
import schedule
import time
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console = Console()

BASE_FILE = Path("restaurants_data.json")   # Original — never touched
LIVE_FILE = Path("live_data.json")          # Generated — browser + scanner read this

# ─────────────────────────────────────────────────
# How much randomness to apply each cycle
# ─────────────────────────────────────────────────
SETTINGS = {
    "price_change_percent":     15,    # Prices shift ±15%
    "offer_expire_chance":      30,    # 30% chance each offer expires
    "new_offer_chance":         40,    # 40% chance restaurant gets new offer
    "status_flip_chance":       20,    # 20% chance open/closed flips
    "rating_change":            0.2,   # Rating shifts ±0.2
    "update_interval_minutes":  30,    # How often to regenerate
}

# Pool of random offers to inject
RANDOM_OFFER_POOL = [
    {"title": "FLASH SALE ₹120 OFF",     "description": "Limited time! ₹120 off on orders above ₹349", "coupon_code": "FLASH120", "min_order": 349,  "max_discount": 120, "expires_in": "2 hours"},
    {"title": "HAPPY HOURS 30% OFF",     "description": "30% off between 2PM-5PM above ₹299",          "coupon_code": "HAPPY30",  "min_order": 299,  "max_discount": 90,  "expires_in": "3 hours"},
    {"title": "HIDDEN GEM ₹200 OFF",     "description": "Secret offer! ₹200 off on orders above ₹499", "coupon_code": "HGEM200",  "min_order": 499,  "max_discount": 200, "expires_in": "1 day"},
    {"title": "WEEKEND SPECIAL 40% OFF", "description": "Weekend deal! 40% off above ₹599",             "coupon_code": "WKND40",   "min_order": 599,  "max_discount": 180, "expires_in": "2 days"},
    {"title": "FLAT ₹75 OFF",            "description": "Quick deal! ₹75 off on orders above ₹199",    "coupon_code": "QUICK75",  "min_order": 199,  "max_discount": 75,  "expires_in": "4 hours"},
    {"title": "SURPRISE ₹250 OFF",       "description": "Surprise offer! ₹250 off above ₹699",         "coupon_code": "SURP250",  "min_order": 699,  "max_discount": 250, "expires_in": "6 hours"},
    {"title": "NIGHT OWL ₹150 OFF",      "description": "Late night deal! ₹150 off above ₹399",        "coupon_code": "NITE150",  "min_order": 399,  "max_discount": 150, "expires_in": "Tonight"},
    {"title": "MEGA MONDAY ₹300 OFF",    "description": "Monday special! ₹300 off above ₹899",         "coupon_code": "MEGA300",  "min_order": 899,  "max_discount": 300, "expires_in": "Today"},
    {"title": "FREE DELIVERY",           "description": "Free delivery on all orders above ₹149",       "coupon_code": "FREEDEL",  "min_order": 149,  "max_discount": 40,  "expires_in": "1 day"},
    {"title": "BIG SAVER ₹500 OFF",      "description": "Massive deal! ₹500 off on orders above ₹1299","coupon_code": "BIGSAVE",  "min_order": 1299, "max_discount": 500, "expires_in": "3 days"},
    {"title": "LUNCH SPECIAL 25% OFF",   "description": "Lunch deal! 25% off between 12PM-3PM",        "coupon_code": "LUNCH25",  "min_order": 249,  "max_discount": 100, "expires_in": "Today"},
    {"title": "DOUBLE DISCOUNT ₹180 OFF","description": "Double savings! ₹180 off above ₹449",         "coupon_code": "DOUBLE18", "min_order": 449,  "max_discount": 180, "expires_in": "2 days"},
]


def load_base():
    """Load original restaurants_data.json"""
    if not BASE_FILE.exists():
        console.print(f"[red]❌ {BASE_FILE} not found![/red]")
        return None
    return json.loads(BASE_FILE.read_text(encoding="utf-8"))


def randomize_price(original_price):
    """Shift price by ±15%"""
    pct = SETTINGS["price_change_percent"] / 100
    factor = random.uniform(1 - pct, 1 + pct)
    new_price = round(original_price * factor / 5) * 5  # Round to nearest ₹5
    return max(29, new_price)  # Minimum ₹29


def randomize_rating(original_rating):
    """Shift rating slightly"""
    delta = random.uniform(-SETTINGS["rating_change"], SETTINGS["rating_change"])
    new_rating = round(original_rating + delta, 1)
    return max(3.0, min(5.0, new_rating))


def randomize_offers(original_offers, restaurant_id):
    """Randomly expire some offers and add new ones"""
    offers = []

    # Keep or expire existing offers
    for offer in original_offers:
        if random.randint(1, 100) <= SETTINGS["offer_expire_chance"]:
            console.print(f"[dim]  ❌ Expired: {offer['title']}[/dim]")
            continue  # This offer expired!
        offers.append(offer)

    # Possibly add a new random offer
    if random.randint(1, 100) <= SETTINGS["new_offer_chance"]:
        new_offer = random.choice(RANDOM_OFFER_POOL).copy()
        new_offer["id"] = f"LIVE_{restaurant_id}_{random.randint(100,999)}"
        new_offer["is_new"] = True  # Mark as newly appeared
        offers.append(new_offer)
        console.print(f"[dim]  🆕 New offer: {new_offer['title']}[/dim]")

    # Always keep at least 1 offer
    if not offers and original_offers:
        offers.append(original_offers[0])

    return offers


def randomize_status(original_status):
    """Randomly flip open/closed"""
    if random.randint(1, 100) <= SETTINGS["status_flip_chance"]:
        return not original_status
    return original_status


def generate_live_data():
    """Main function — generates live_data.json from base data"""
    console.print(f"\n[cyan]🔄 Generating live data at {datetime.now().strftime('%I:%M %p')}...[/cyan]")

    base = load_base()
    if not base:
        return False

    live = {
        "meta": {
            **base["meta"],
            "type": "live",
            "generated_at": datetime.now().isoformat(),
            "next_update": f"In {SETTINGS['update_interval_minutes']} minutes",
            "cycle": int(datetime.now().timestamp()),
        },
        "restaurants": []
    }

    changes_summary = {
        "price_changes": 0,
        "offers_expired": 0,
        "new_offers": 0,
        "status_changed": 0,
    }

    for r in base["restaurants"]:
        console.print(f"[dim]Processing {r['name']}...[/dim]")

        # Count original offers
        original_offer_count = len(r["offers"])

        # Randomize offers
        new_offers = randomize_offers(r["offers"], r["id"])
        offers_expired = original_offer_count - len([o for o in new_offers if not o.get("is_new")])
        new_offer_count = len([o for o in new_offers if o.get("is_new")])
        changes_summary["offers_expired"] += max(0, offers_expired)
        changes_summary["new_offers"] += new_offer_count

        # Randomize status
        new_status = randomize_status(r["is_open"])
        if new_status != r["is_open"]:
            changes_summary["status_changed"] += 1
            status_change = "🟢 Opened" if new_status else "🔴 Closed"
            console.print(f"[dim]  {status_change}: {r['name']}[/dim]")

        # Randomize menu prices
        new_menu = []
        for category in r["menu"]:
            new_items = []
            for item in category["items"]:
                old_price = item["price"]
                new_price = randomize_price(old_price)
                if new_price != old_price:
                    changes_summary["price_changes"] += 1
                new_items.append({**item, "price": new_price, "original_price": old_price})
            new_menu.append({**category, "items": new_items})

        # Randomize rating
        new_rating = randomize_rating(r["rating"])

        # Build live restaurant
        live_restaurant = {
            **r,
            "rating":    new_rating,
            "is_open":   new_status,
            "offers":    new_offers,
            "menu":      new_menu,
            "last_updated": datetime.now().strftime("%I:%M %p"),
        }
        live["restaurants"].append(live_restaurant)

    # Save live_data.json
    LIVE_FILE.write_text(json.dumps(live, indent=2, ensure_ascii=False), encoding="utf-8")

    console.print(Panel(
        f"[bold green]✅ live_data.json updated![/bold green]\n\n"
        f"  💰 Price changes:    {changes_summary['price_changes']} items\n"
        f"  ❌ Offers expired:   {changes_summary['offers_expired']}\n"
        f"  🆕 New offers:       {changes_summary['new_offers']}\n"
        f"  🔄 Status changes:   {changes_summary['status_changed']} restaurants\n\n"
        f"  📄 Saved to: live_data.json\n"
        f"  ⏰ Next update in {SETTINGS['update_interval_minutes']} mins",
        border_style="green"
    ))
    return True


def main():
    console.print(Panel(
        "[bold orange1]🍜 FOOD DATA ENGINE[/bold orange1]\n\n"
        f"📄 Base file:    restaurants_data.json\n"
        f"📄 Live file:    live_data.json\n"
        f"🔄 Updates every {SETTINGS['update_interval_minutes']} minutes\n\n"
        "[dim]Keep this running while using browser + scanner![/dim]",
        border_style="orange1"
    ))

    if not BASE_FILE.exists():
        console.print("[red]❌ restaurants_data.json not found! Put it in the same folder.[/red]")
        return

    # Generate immediately on start
    generate_live_data()

    # Schedule future updates
    schedule.every(SETTINGS["update_interval_minutes"]).minutes.do(generate_live_data)

    console.print(f"\n[green]✅ Engine running! Auto-updates every {SETTINGS['update_interval_minutes']} mins[/green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        console.print("\n[yellow]👋 Data engine stopped![/yellow]")


if __name__ == "__main__":
    main()
