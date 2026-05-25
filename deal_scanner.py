"""
╔══════════════════════════════════════════════════════════╗
║              DEAL SCANNER                                ║
║   17 categories + Clean UX + Precise keywords            ║
║   Best match + All restaurants + Split order logic       ║
║   Mix mode + Combo finder + Smart budget                 ║
╚══════════════════════════════════════════════════════════╝

SETUP:
------
1. Run data_engine.py first to generate live_data.json
2. pip install rich schedule plyer
3. python deal_scanner.py
"""

import json
import math
import time
import schedule
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
LIVE_FILE = Path("live_data.json")
BASE_FILE = Path("restaurants_data.json")

# ─────────────────────────────────────────────────
#  ⚙️  CONFIG
# ─────────────────────────────────────────────────
CONFIG = {
    "budget":                None,   # Not set yet — user must set via Option 4
    "cuisine_quantities":    {},
    "veg_preferences":       {},
    "scan_interval_minutes": 60,
    "notify_desktop":        True,
}
# ─────────────────────────────────────────────────


# ══════════════════════════════════════════════════
# 📦 DATA LOADER
# ══════════════════════════════════════════════════
def load_restaurants():
    if LIVE_FILE.exists():
        data = json.loads(LIVE_FILE.read_text(encoding="utf-8"))
        generated_at = data.get("meta", {}).get("generated_at", "")
        if generated_at:
            ts = datetime.fromisoformat(generated_at)
            mins_ago = int((datetime.now() - ts).total_seconds() / 60)
            console.print(f"[green]📄 Reading live_data.json[/green] [dim](updated {mins_ago} mins ago)[/dim]")
        return data.get("restaurants", [])
    elif BASE_FILE.exists():
        console.print(f"[yellow]⚠ Using restaurants_data.json (run data_engine.py for live data)[/yellow]")
        data = json.loads(BASE_FILE.read_text(encoding="utf-8"))
        return data.get("restaurants", [])
    else:
        console.print("[red]❌ No data file found![/red]")
        return []


def get_all_cuisines():
    """Return curated 17-category list instead of raw restaurant tags"""
    return CURATED_CUISINES


# ══════════════════════════════════════════════════
# 💰 BILLING ENGINE
# ══════════════════════════════════════════════════
def calc_bill(item_total, discount=0):
    """Full bill with delivery, GST, platform fee"""
    delivery    = 0 if item_total >= 299 else 40
    gst         = math.floor((item_total + delivery) * 0.05 + 0.5)  # Standard rounding — matches browser JS
    platform    = 5
    grand_total = item_total + delivery + gst + platform - discount
    return {
        "item_total":  item_total,
        "delivery":    delivery,
        "gst":         gst,
        "platform":    platform,
        "discount":    discount,
        "grand_total": max(0, grand_total),
    }


def best_coupon_for(restaurant, order_total):
    """Find best applicable coupon for an order total"""
    best = None
    for offer in restaurant.get("offers", []):
        if offer["min_order"] <= order_total:
            if best is None or offer["max_discount"] > best["max_discount"]:
                best = offer
    return best


# ─────────────────────────────────────────────────
# 17 Curated food categories — precise & user-friendly
# Based on actual menu items in the data
# ─────────────────────────────────────────────────
CUISINE_KEYWORDS = {
    "🍗 Biryani":                ["biryani", "dum biryani"],
    "🍕 Pizza":                   ["pizza", "margherita", "farm house", "double cheese"],
    "🍔 Burger & Combo":          ["burger", "zinger", "mcaloo", "big mac", "tower burger", "combo"],
    "🍗 Fried Chicken":           ["hot & crispy", "popcorn chicken", "chicken wings", "chicken 65", "crispy chicken"],
    "🍟 Fries & Sides":           ["french fries", "fries", "nuggets", "garlic breadsticks", "stuffed garlic bread"],
    "🥟 Momos":                   ["momo"],
    "🍜 Noodles, Rice & Soup":    ["noodles", "fried rice", "hakka", "jeera rice", "soup"],
    "🍝 Pasta":                   ["pasta"],   # item-name match only — see find_cheapest_item
    "🥞 Dosa":                    ["dosa", "pesarattu"],
    "🫙 Tiffin":                  ["idli", "vada", "upma", "thali", "sambar"],
    "🍛 Curry":                   ["butter chicken", "paneer butter masala", "dal makhani", "curry"],
    "🔥 Kebabs & Tikka":          ["chicken tikka", "paneer tikka", "seekh kebab", "boti kebab", "pathar ka gosht", "kebab"],
    # Note: pizza items are excluded in find_cheapest_item/find_all_items via pizza_exclude check
    "🥩 Haleem":                  ["haleem"],
    "🍖 Grills & Platters":       ["grilled chicken platter", "veg bbq platter", "grill", "bbq platter"],
    "🫓 Breads":                  ["naan", "roti", "tandoori roti"],
    "🥤 Beverages":               ["pepsi", "lemonade", "coke", "mcflurry", "juice", "drink"],
    "🍮 Desserts":                ["meetha", "gulab jamun", "rasmalai", "firni", "cake", "banana foster", "kheer", "ice cream"],
}

# Curated display order — what user sees in the scanner menu
CURATED_CUISINES = list(CUISINE_KEYWORDS.keys())

def restaurant_has_cuisine(restaurant, cuisine):
    """Strictly check if restaurant actually serves this cuisine"""
    rest_cuisine = restaurant["cuisine"].lower()
    # Direct cuisine type match
    if cuisine.lower() in rest_cuisine or rest_cuisine in cuisine.lower():
        return True
    # Keyword match in menu items
    keywords = CUISINE_KEYWORDS.get(cuisine, [cuisine.lower()])
    for cat in restaurant.get("menu", []):
        for item in cat.get("items", []):
            item_text = item["name"].lower()
            if any(kw in item_text for kw in keywords):
                return True
    return False


def restaurant_has_cuisines(restaurant, cuisine_list):
    """Check if restaurant has ALL requested cuisines"""
    return all(restaurant_has_cuisine(restaurant, c) for c in cuisine_list)


def check_veg_availability(restaurants, cuisine):
    """Check what veg types are available for a cuisine across ALL restaurants"""
    keywords       = CUISINE_KEYWORDS.get(cuisine, [cuisine.lower()])
    has_veg        = False
    has_non_veg    = False
    item_name_only = cuisine == "🍝 Pasta"

    for r in restaurants:
        for cat in r.get("menu", []):
            for item in cat.get("items", []):
                item_text = item["name"].lower()
                cat_text  = cat["category"].lower()
                if item_name_only:
                    match = any(kw in item_text for kw in keywords)
                else:
                    match = any(kw in item_text or kw in cat_text for kw in keywords)
                if match:
                    if item.get("is_veg", True):
                        has_veg = True
                    else:
                        has_non_veg = True
                if has_veg and has_non_veg:
                    return "both"

    if has_veg and has_non_veg:
        return "both"
    elif has_veg:
        return "veg_only"
    elif has_non_veg:
        return "non_veg_only"
    else:
        return "unknown"


def ask_veg_preference(cuisine, restaurants, qty=1):
    """
    Smart veg/non-veg selector.
    - If only veg exists     → auto-select veg, inform user
    - If only non-veg exists → auto-select non-veg, inform user
    - If both exist          → ask user to choose (option 4 Mix appears when qty ≥ 2)
    Returns: "veg", "non-veg", "any", or {"mix": True, "veg_qty": X, "non_veg_qty": Y}
    """
    availability = check_veg_availability(restaurants, cuisine)

    if availability == "veg_only":
        console.print(f"  [dim]ℹ️  Only [green]veg[/green] items available for {cuisine} — auto-selected Veg[/dim]")
        return "veg"
    elif availability == "non_veg_only":
        console.print(f"  [dim]ℹ️  Only [red]non-veg[/red] items available for {cuisine} — auto-selected Non-Veg[/dim]")
        return "non-veg"
    else:
        # Both exist — ask user
        show_mix = qty >= 2
        console.print(f"\n  [bold]🥗 {cuisine} preference:[/bold]")
        console.print(f"    [bold]1[/bold] — 🟢 Veg only")
        console.print(f"    [bold]2[/bold] — 🔴 Non-Veg only")
        console.print(f"    [bold]3[/bold] — 🟡 Any (cheapest wins)")
        if show_mix:
            console.print(f"    [bold]4[/bold] — 🔀 Mix (split: X Veg + Y Non-Veg)")
        valid_choices = ["", "1", "2", "3"] + (["4"] if show_mix else [])
        while True:
            choice = input(f"  Your choice [3]: ").strip()
            if choice not in valid_choices:
                max_opt = "4" if show_mix else "3"
                console.print(f"  [red]Invalid, enter 1–{max_opt}[/red]")
                continue
            if choice == "" or choice == "3":
                console.print(f"  [green]✅ Any (cheapest) for {cuisine}[/green]")
                return "any"
            elif choice == "1":
                console.print(f"  [green]✅ Veg only for {cuisine}[/green]")
                return "veg"
            elif choice == "2":
                console.print(f"  [green]✅ Non-Veg only for {cuisine}[/green]")
                return "non-veg"
            elif choice == "4":
                # Ask split quantities
                while True:
                    try:
                        console.print(f"  [dim]Total qty: {qty}. How to split?[/dim]")
                        veg_qty = input(f"    How many Veg {cuisine}? [1]: ").strip()
                        veg_qty = int(veg_qty) if veg_qty else 1
                        non_veg_qty = qty - veg_qty
                        if veg_qty < 1 or non_veg_qty < 1:
                            console.print(f"  [red]Both Veg and Non-Veg qty must be ≥ 1 (total must equal {qty})[/red]")
                            continue
                        console.print(f"  [green]✅ Mix: {veg_qty}× Veg + {non_veg_qty}× Non-Veg {cuisine}[/green]")
                        return {"mix": True, "veg_qty": veg_qty, "non_veg_qty": non_veg_qty}
                    except ValueError:
                        console.print("  [red]Enter a valid number[/red]")



def find_cheapest_item(restaurant, cuisine, veg_pref="any"):
    """Find best item by lowest grand total after coupon — not just cheapest price"""
    keywords  = CUISINE_KEYWORDS.get(cuisine, [cuisine.lower()])
    best_item        = None
    best_grand_total = None

    item_name_only      = cuisine == "🍝 Pasta"
    kebab_exclude_pizza = cuisine == "🔥 Kebabs & Tikka"

    for cat in restaurant.get("menu", []):
        for item in cat.get("items", []):
            item_text = item["name"].lower()
            cat_text  = cat["category"].lower()
            if item_name_only:
                match = any(kw in item_text for kw in keywords)
            else:
                match = any(kw in item_text or kw in cat_text for kw in keywords)
            if not match:
                continue
            # Exclude pizza items from Kebabs & Tikka category
            if kebab_exclude_pizza and "pizza" in item_text:
                continue
            # ── Veg/Non-veg filter ──────────────────
            item_is_veg = item.get("is_veg", True)
            if veg_pref == "veg" and not item_is_veg:
                continue
            if veg_pref == "non-veg" and item_is_veg:
                continue
            # ── Pick by lowest grand total after coupon ──
            coupon      = best_coupon_for(restaurant, item["price"])
            discount    = coupon["max_discount"] if coupon else 0
            bill        = calc_bill(item["price"], discount)
            grand_total = bill["grand_total"]

            if best_item is None or grand_total < best_grand_total:
                best_item        = item
                best_grand_total = grand_total

    return best_item


def find_all_items(restaurant, cuisine, veg_pref="any"):
    """Find ALL matching items respecting veg/non-veg filter — sorted cheapest first"""
    keywords            = CUISINE_KEYWORDS.get(cuisine, [cuisine.lower()])
    item_name_only      = cuisine == "🍝 Pasta"
    kebab_exclude_pizza = cuisine == "🔥 Kebabs & Tikka"
    matched = []

    for cat in restaurant.get("menu", []):
        for item in cat.get("items", []):
            item_text = item["name"].lower()
            cat_text  = cat["category"].lower()
            if item_name_only:
                match = any(kw in item_text for kw in keywords)
            else:
                match = any(kw in item_text or kw in cat_text for kw in keywords)
            if not match:
                continue
            # Exclude pizza items from Kebabs & Tikka category
            if kebab_exclude_pizza and "pizza" in item_text:
                continue
            item_is_veg = item.get("is_veg", True)
            if veg_pref == "veg"     and not item_is_veg: continue
            if veg_pref == "non-veg" and item_is_veg:     continue
            matched.append(item)

    return sorted(matched, key=lambda x: x["price"])


# ══════════════════════════════════════════════════
# 🔍 MAIN SCANNER
# ══════════════════════════════════════════════════
def run_quantity_scan():
    """Scan with cuisine quantities — full combo logic"""
    budget           = CONFIG["budget"]
    cuisine_qtys     = CONFIG["cuisine_quantities"]
    restaurants      = load_restaurants()

    if not restaurants:
        return

    if budget is None:
        console.print("[yellow]⚠ Set budget to scan! (Option 4)[/yellow]")
        return

    if not cuisine_qtys:
        console.print("[yellow]⚠ Set cuisines to scan! (Option 3)[/yellow]")
        return

    veg_pref_lines = ""
    for cuisine, qty in cuisine_qtys.items():
        pref = CONFIG["veg_preferences"].get(cuisine, "any")
        if isinstance(pref, dict) and pref.get("mix"):
            pref_label = f"🔀 Mix ({pref['veg_qty']}× 🟢 + {pref['non_veg_qty']}× 🔴)"
        else:
            pref_label = {"veg": "🟢 Veg", "non-veg": "🔴 Non-Veg", "any": "🟡 Any"}.get(pref, "🟡 Any")
        veg_pref_lines += f"\n   {qty}× {cuisine} ({pref_label})"

    console.print(Panel(
        f"[bold cyan]🔍 QUANTITY SCAN STARTED[/bold cyan]\n\n"
        f"📍 Kompally, Hyderabad\n"
        f"💰 Budget: ₹{budget}\n"
        f"🛒 Your order:{veg_pref_lines}\n"
        f"⏰ {datetime.now().strftime('%I:%M %p, %d %b %Y')}",
        border_style="cyan"
    ))

    cuisine_list = list(cuisine_qtys.keys())

    # ── Step 1: Scan all restaurants ──────────────
    console.print("\n[cyan]Scanning restaurants...[/cyan]")
    single_results  = []   # Restaurants with ALL cuisines
    partial_results = {}   # cuisine → list of restaurants

    for r in restaurants:
        status = "[green]OPEN[/green]" if r["is_open"] else "[red]CLOSED[/red]"
        console.print(f"[dim]  📖 {r['name']} ({r['cuisine']}) — {status}[/dim]")
        time.sleep(0.2)

        has_all = restaurant_has_cuisines(r, cuisine_list)

        # Calculate order total for this restaurant
        order_items  = []
        order_total  = 0
        all_found    = True

        for cuisine, qty in cuisine_qtys.items():
            veg_pref = CONFIG["veg_preferences"].get(cuisine, "any")

            if isinstance(veg_pref, dict) and veg_pref.get("mix"):
                # ── Mix mode: find cheapest veg + cheapest non-veg separately ──
                veg_qty     = veg_pref["veg_qty"]
                non_veg_qty = veg_pref["non_veg_qty"]

                veg_item     = find_cheapest_item(r, cuisine, "veg")
                non_veg_item = find_cheapest_item(r, cuisine, "non-veg")

                if veg_item and non_veg_item:
                    for sub_item, sub_qty, sub_label in [
                        (veg_item, veg_qty, "Veg"),
                        (non_veg_item, non_veg_qty, "Non-Veg"),
                    ]:
                        order_items.append({
                            "name":     sub_item["name"],
                            "price":    sub_item["price"],
                            "qty":      sub_qty,
                            "cuisine":  cuisine,
                            "mix_label": sub_label,
                            "subtotal": sub_item["price"] * sub_qty,
                        })
                        order_total += sub_item["price"] * sub_qty

                    # Track in partial_results using cheapest overall price
                    cheapest_mix = veg_item if veg_item["price"] <= non_veg_item["price"] else non_veg_item
                    if cuisine not in partial_results:
                        partial_results[cuisine] = []
                    partial_results[cuisine].append({
                        "restaurant":    r["name"],
                        "is_open":       r["is_open"],
                        "delivery_time": r.get("delivery_time", ""),
                        "cuisine":       cuisine,
                        "item":          f"{veg_qty}× {veg_item['name']} + {non_veg_qty}× {non_veg_item['name']}",
                        "price":         cheapest_mix["price"],
                        "qty":           qty,
                        "subtotal":      veg_item["price"] * veg_qty + non_veg_item["price"] * non_veg_qty,
                        "restaurant_obj": r,
                    })
                else:
                    all_found = False   # Restaurant doesn't have both veg + non-veg

            else:
                # ── Normal mode ──────────────────────────────────────────────
                item = find_cheapest_item(r, cuisine, veg_pref)
                if item:
                    order_items.append({
                        "name":    item["name"],
                        "price":   item["price"],
                        "qty":     qty,
                        "cuisine": cuisine,
                        "subtotal": item["price"] * qty
                    })
                    order_total += item["price"] * qty
                    # Track per-cuisine for split orders
                    if cuisine not in partial_results:
                        partial_results[cuisine] = []
                    partial_results[cuisine].append({
                        "restaurant":   r["name"],
                        "is_open":      r["is_open"],
                        "delivery_time": r.get("delivery_time", ""),
                        "cuisine":      cuisine,
                        "item":         item["name"],
                        "price":        item["price"],
                        "qty":          qty,
                        "subtotal":     item["price"] * qty,
                        "restaurant_obj": r
                    })
                else:
                    all_found = False

        if all_found and order_items:
            coupon      = best_coupon_for(r, order_total)
            discount    = coupon["max_discount"] if coupon else 0
            bill        = calc_bill(order_total, discount)

            single_results.append({
                "restaurant":    r["name"],
                "is_open":       r["is_open"],
                "delivery_time": r.get("delivery_time", ""),
                "rating":        r.get("rating", 0),
                "order_items":   order_items,
                "order_total":   order_total,
                "coupon":        coupon,
                "discount":      discount,
                "bill":          bill,
                "fits_budget":   bill["grand_total"] <= budget,
                "over_budget_by": max(0, bill["grand_total"] - budget),
            })

    # Sort: OPEN restaurants first, then by grand total, then by rating (higher = better) as tiebreaker
    single_results.sort(key=lambda x: (0 if x["is_open"] else 1, x["bill"]["grand_total"], -x["rating"]))

    # ── Step 2: Show Results ───────────────────────
    if single_results:
        show_single_restaurant_results(single_results, budget, cuisine_qtys, restaurants)
    else:
        console.print(Panel(
            "[yellow]😔 No single restaurant found with all your cuisines![/yellow]\n"
            "Showing split order suggestion below...",
            border_style="yellow"
        ))

    # ── Step 3: Split order (if needed) ───────────
    split_total = None
    if len(cuisine_list) > 1:
        split_total = show_split_order(partial_results, budget, cuisine_qtys)

    # Notification
    if single_results:
        best = single_results[0]
        notify_desktop(
            f"🔥 Best deal: {best['restaurant']}",
            f"₹{best['bill']['grand_total']} for your order! Save ₹{best['discount']}"
        )
    elif split_total is not None:
        notify_desktop(
            f"🔀 Split Order Found!",
            f"Combined total: ₹{split_total} across {len(cuisine_list)} restaurants"
        )


def show_single_restaurant_results(results, budget, cuisine_qtys, restaurants_data):
    """Show best match + all restaurants with full bill"""

    # ── BEST MATCH ────────────────────────────────
    best = results[0]
    bill = best["bill"]

    # Budget warning
    if best["bill"]["grand_total"] > budget:
        console.print(f"\n[bold yellow]⚠ BUDGET WARNING:[/bold yellow]")
        console.print(f"[yellow]  Cheapest option ₹{best['bill']['grand_total']} exceeds your ₹{budget} budget by ₹{best['over_budget_by']}[/yellow]")
        if best["coupon"]:
            console.print(f"[yellow]  But coupon {best['coupon']['coupon_code']} saves ₹{best['discount']} — consider it![/yellow]")
    else:
        console.print(f"\n[green]✅ Found {len(results)} restaurant(s) within your ₹{budget} budget![/green]")

    delivery_str = "FREE 🆓" if bill["delivery"] == 0 else f"₹{bill['delivery']}"

    items_str = "\n".join(
        f"   {i['qty']}× {i['name']} "
        f"({'🟢 Veg' if i.get('mix_label') == 'Veg' else '🔴 Non-Veg' if i.get('mix_label') == 'Non-Veg' else i['cuisine']}) "
        f"— ₹{i['price']} × {i['qty']} = ₹{i['subtotal']}"
        for i in best["order_items"]
    )

    coupon_line = f"   Coupon ({best['coupon']['coupon_code']}): [bold red]-₹{best['discount']}[/bold red]\n" if best["coupon"] else ""

    console.print(Panel(
        f"[bold yellow]🏆 BEST MATCH — {best['restaurant']}[/bold yellow]\n"
        f"   ⭐ {best['rating']}  •  🕐 {best['delivery_time']}  •  "
        f"{'[green]OPEN[/green]' if best['is_open'] else '[red]CLOSED[/red]'}\n\n"
        f"[bold]🛒 Your Order:[/bold]\n{items_str}\n\n"
        f"[bold]🧾 Bill Breakdown:[/bold]\n"
        f"   Item Total:      ₹{bill['item_total']}\n"
        f"   Delivery:        {delivery_str}\n"
        f"   GST (5%):        ₹{bill['gst']}\n"
        f"   Platform Fee:    ₹{bill['platform']}\n"
        f"{coupon_line}"
        f"   ─────────────────────────\n"
        f"   [bold green]Grand Total:     ₹{bill['grand_total']}[/bold green]"
        + (f"\n\n   [bold magenta]Best Coupon: {best['coupon']['coupon_code']} — {best['coupon']['title']}[/bold magenta]" if best["coupon"] else "")
        + (f"\n   [green]🎉 You save ₹{best['discount']}![/green]" if best["discount"] > 0 else ""),
        border_style="yellow"
    ))

    # ── ALL ITEMS TABLE ───────────────────────────
    # Shows every matching item per restaurant (respecting veg filter)
    # so user can pick the one they actually want
    cuisine_list = list(cuisine_qtys.keys())

    # Only show table when there are results to compare
    table = Table(
        title="📋 All Available Items for Your Order",
        border_style="cyan", show_lines=True
    )
    table.add_column("Restaurant",  style="bold white", max_width=20)
    table.add_column("Status",      max_width=8)
    table.add_column("⭐",           max_width=5)
    table.add_column("Delivery",    style="dim",        max_width=11)
    table.add_column("Item",        style="white",      max_width=26)
    table.add_column("Type",        max_width=5)
    table.add_column("Price",       style="yellow",     max_width=8)
    table.add_column("Best Coupon", style="magenta",    max_width=12)
    table.add_column("You Save",    style="bold green", max_width=10)
    table.add_column("Grand Total", style="bold cyan",  max_width=12)
    table.add_column("Budget",      max_width=10)

    # Build all rows first so we can sort by Grand Total
    all_rows = []
    for r_data in restaurants_data:
        r_name    = r_data["name"]
        is_open   = r_data["is_open"]
        status    = "[green]OPEN[/green]" if is_open else "[red]CLOSED[/red]"
        rating_num = r_data.get("rating", 0)
        rating    = str(rating_num)
        delivery  = r_data.get("delivery_time", "-")

        if len(cuisine_list) == 1:
            cuisine  = cuisine_list[0]
            veg_pref = CONFIG["veg_preferences"].get(cuisine, "any")
            if isinstance(veg_pref, dict):
                veg_pref = "any"
            all_items = find_all_items(r_data, cuisine, veg_pref)
            for item in all_items:
                veg_icon      = "🟢" if item.get("is_veg") else "🔴"
                item_total    = item["price"]
                coupon        = best_coupon_for(r_data, item_total)
                discount      = coupon["max_discount"] if coupon else 0
                bill          = calc_bill(item_total, discount)
                coupon_code   = coupon["coupon_code"] if coupon else "-"
                you_save      = f"₹{discount}" if discount > 0 else "-"
                fits          = "[green]✅ OK[/green]" if bill["grand_total"] <= budget else f"[red]↑₹{bill['grand_total']-budget}[/red]"
                all_rows.append({
                    "is_open":     is_open,
                    "grand_total": bill["grand_total"],
                    "rating":      rating_num,
                    "row": (r_name[:20], status, rating, delivery, item["name"][:26], veg_icon, f"₹{item['price']}", coupon_code, you_save, f"₹{bill['grand_total']}", fits)
                })
        else:
            for res in results:
                if res["restaurant"] != r_name:
                    continue
                b             = res["bill"]
                budget_status = "[green]✅ OK[/green]" if res["fits_budget"] else f"[red]↑₹{res['over_budget_by']}[/red]"
                items_summary = ", ".join(f"{i['qty']}×{i['name']}" for i in res["order_items"])
                coupon_code   = res["coupon"]["coupon_code"] if res["coupon"] else "-"
                you_save      = f"₹{res['discount']}" if res["discount"] > 0 else "-"
                all_rows.append({
                    "is_open":     is_open,
                    "grand_total": b["grand_total"],
                    "rating":      rating_num,
                    "row": (r_name[:20], status, rating, delivery, items_summary[:26], "-", f"₹{b['item_total']}", coupon_code, you_save, f"₹{b['grand_total']}", budget_status)
                })

    # Sort: OPEN first, then by Grand Total cheapest first, then by rating (higher = better) as tiebreaker
    all_rows.sort(key=lambda x: (0 if x["is_open"] else 1, x["grand_total"], -x.get("rating", 0)))

    for entry in all_rows:
        table.add_row(*entry["row"])

    if all_rows:
        console.print(table)


def show_split_order(partial_results, budget, cuisine_qtys):
    """Show split order suggestion when ordering from multiple restaurants"""
    console.print("\n[bold cyan]🔀 SPLIT ORDER ANALYSIS[/bold cyan]")

    cuisine_list = list(cuisine_qtys.keys())

    # Check if ALL cuisines are available
    all_available = all(c in partial_results and partial_results[c] for c in cuisine_list)

    if not all_available:
        missing = [c for c in cuisine_list if c not in partial_results or not partial_results[c]]
        console.print(f"[red]❌ These cuisines not found anywhere: {', '.join(missing)}[/red]")
        return

    # Find best restaurant per cuisine
    split_order  = []
    split_total  = 0

    console.print(Panel(
        "[dim]Tip: Same restaurant = one delivery fee. Split order = multiple delivery fees[/dim]",
        border_style="dim"
    ))

    for cuisine in cuisine_list:
        def sort_key(x):
            c = best_coupon_for(x["restaurant_obj"], x["subtotal"])
            d = c["max_discount"] if c else 0
            b = calc_bill(x["subtotal"], d)
            return (0 if x["is_open"] else 1, b["grand_total"])

        options  = sorted(partial_results[cuisine], key=sort_key)
        best     = options[0]
        coupon   = best_coupon_for(best["restaurant_obj"], best["subtotal"])
        discount = coupon["max_discount"] if coupon else 0
        bill     = calc_bill(best["subtotal"], discount)

        split_order.append({
            "cuisine":    cuisine,
            "restaurant": best["restaurant"],
            "is_open":    best["is_open"],
            "delivery_time": best["delivery_time"],
            "item":       best["item"],
            "qty":        best["qty"],
            "subtotal":   best["subtotal"],
            "coupon":     coupon,
            "discount":   discount,
            "bill":       bill,
        })
        split_total += bill["grand_total"]

    # Show each restaurant separately
    for idx, order in enumerate(split_order, 1):
        b = order["bill"]
        delivery_str = "FREE 🆓" if b["delivery"] == 0 else f"₹{b['delivery']}"
        console.print(Panel(
            f"[bold]Order {idx}: {order['cuisine']} from {order['restaurant']}[/bold]  "
            f"{'[green]OPEN[/green]' if order['is_open'] else '[red]CLOSED[/red]'}  "
            f"🕐 {order['delivery_time']}\n\n"
            f"   {order['qty']}× {order['item']} = ₹{order['subtotal']}\n\n"
            f"   Item Total:   ₹{b['item_total']}\n"
            f"   Delivery:     {delivery_str}\n"
            f"   GST (5%):     ₹{b['gst']}\n"
            f"   Platform Fee: ₹{b['platform']}\n"
            + (f"   Coupon:      -₹{order['discount']} ({order['coupon']['coupon_code']})\n" if order["coupon"] else "")
            + f"   ─────────────────\n"
            f"   [bold]This order: ₹{b['grand_total']}[/bold]",
            border_style="blue"
        ))

    # Split total summary
    fits = split_total <= budget
    console.print(Panel(
        f"[bold]💰 SPLIT ORDER TOTAL SUMMARY[/bold]\n\n"
        + "\n".join(f"   Order {i+1} ({o['restaurant']}): ₹{o['bill']['grand_total']}" for i, o in enumerate(split_order))
        + f"\n   ─────────────────────────────\n"
        f"   [bold {'green' if fits else 'red'}]Combined Total: ₹{split_total}[/bold {'green' if fits else 'red'}]\n"
        f"   Your Budget:    ₹{budget}\n"
        f"   {'[green]✅ Within budget![/green]' if fits else f'[red]⚠ Over budget by ₹{split_total - budget}[/red]'}",
        border_style="green" if fits else "red"
    ))
    return split_total


# ══════════════════════════════════════════════════
# ⚙️  CUISINE + QUANTITY SELECTION
# ══════════════════════════════════════════════════
def select_cuisine_quantities():
    """Step 1: Select cuisines. Step 2: Enter quantity per cuisine."""
    cuisines = get_all_cuisines()

    # ── Step 1: Select cuisines ───────────────────
    console.print("\n[bold cyan]🍽  Step 1 — Select Cuisines:[/bold cyan]")
    for i, c in enumerate(cuisines, 1):
        already = "✅" if c in CONFIG["cuisine_quantities"] else "  "
        console.print(f"  [bold]{i}[/bold] — {already} {c}")

    console.print("\n[dim]Enter numbers (e.g. 1,3 for Biryani + South Indian)[/dim]")
    console.print("[dim]Press 0 to clear all[/dim]\n")

    raw = input("Select cuisines: ").strip()

    if raw == "0" or raw == "":
        CONFIG["cuisine_quantities"] = {}
        console.print("[green]✅ Cleared all cuisines[/green]")
        return

    try:
        indices  = [int(x.strip()) for x in raw.split(",")]
        selected = [cuisines[i-1] for i in indices if 1 <= i <= len(cuisines)]
    except ValueError:
        console.print("[red]Invalid input[/red]")
        return

    if not selected:
        console.print("[red]No valid cuisines selected[/red]")
        return

    # ── Step 2: Quantity per cuisine ─────────────
    console.print(f"\n[bold cyan]📦 Step 2 — Enter Quantity for each cuisine:[/bold cyan]")
    console.print("[dim]Enter how many items you want (e.g. 2 for 2 biryanis)[/dim]\n")

    new_qtys = {}
    for cuisine in selected:
        current = CONFIG["cuisine_quantities"].get(cuisine, 1)
        try:
            val = input(f"  How many {cuisine}? [{current}]: ").strip()
            qty = int(val) if val else current
            qty = max(1, qty)
            new_qtys[cuisine] = qty
            console.print(f"  [green]✅ {qty}× {cuisine}[/green]")
        except ValueError:
            new_qtys[cuisine] = current
            console.print(f"  [yellow]Invalid, using {current}× {cuisine}[/yellow]")

    CONFIG["cuisine_quantities"] = new_qtys

    # ── Step 3: Veg / Non-veg preference ─────────
    console.print(f"\n[bold cyan]🥗 Step 3 — Veg / Non-Veg preference:[/bold cyan]")
    console.print("[dim]We'll check what's actually available for each cuisine first[/dim]\n")

    restaurants = load_restaurants()
    new_veg_prefs = {}
    for cuisine in selected:
        qty = new_qtys.get(cuisine, 1)
        pref = ask_veg_preference(cuisine, restaurants, qty=qty)
        new_veg_prefs[cuisine] = pref

    CONFIG["veg_preferences"] = new_veg_prefs

    # Show summary
    pref_label_map = {"veg": "🟢 Veg", "non-veg": "🔴 Non-Veg", "any": "🟡 Any"}
    console.print("\n[bold green]✅ Your Order Summary:[/bold green]")
    for cuisine, qty in new_qtys.items():
        raw_pref = new_veg_prefs.get(cuisine, "any")
        if isinstance(raw_pref, dict) and raw_pref.get("mix"):
            pref = f"🔀 Mix ({raw_pref['veg_qty']}× 🟢 Veg + {raw_pref['non_veg_qty']}× 🔴 Non-Veg)"
        else:
            pref = pref_label_map.get(raw_pref, "🟡 Any")
        console.print(f"  {qty}× {cuisine}  {pref}")

    console.print("\n[green]✅ Order set![/green]")
    input("Press Enter to continue...")


# ══════════════════════════════════════════════════
# 🔔 NOTIFICATIONS
# ══════════════════════════════════════════════════
def notify_desktop(title, message):
    if not CONFIG["notify_desktop"]:
        return
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="🍜 Deal Scanner", timeout=10)
    except Exception:
        console.print(f"\n[bold yellow]🔔 {title}: {message}[/bold yellow]")


# ══════════════════════════════════════════════════
# ⏰ BACKGROUND MONITOR
# ══════════════════════════════════════════════════
def background_monitor():
    if not CONFIG["cuisine_quantities"] or CONFIG["budget"] is None:
        no_budget   = CONFIG["budget"] is None
        no_cuisines = not CONFIG["cuisine_quantities"]
        if no_budget and no_cuisines:
            console.print("[yellow]⚠ Set budget and cuisines to scan! (Options 3 & 4)[/yellow]")
        elif no_budget:
            console.print("[yellow]⚠ Set budget to scan! (Option 4)[/yellow]")
        elif no_cuisines:
            console.print("[yellow]⚠ Set cuisines to scan! (Option 3)[/yellow]")
        return

    console.print(Panel(
        f"[bold green]🤖 Background Monitor Active![/bold green]\n"
        f"Auto-scanning every [bold]{CONFIG['scan_interval_minutes']} minutes[/bold]\n"
        f"Your order: {', '.join(f'{q}× {c}' for c, q in CONFIG['cuisine_quantities'].items())}\n"
        f"[dim]Press Ctrl+C to stop[/dim]",
        border_style="green"
    ))
    run_quantity_scan()
    schedule.every(CONFIG["scan_interval_minutes"]).minutes.do(run_quantity_scan)
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        console.print("\n[yellow]👋 Monitor stopped![/yellow]")


# ══════════════════════════════════════════════════
# ⚙️  SETTINGS
# ══════════════════════════════════════════════════
def edit_settings():
    while True:
        order_summary = ", ".join(f"{q}× {c}" for c, q in CONFIG["cuisine_quantities"].items()) if CONFIG["cuisine_quantities"] else "Not set"
        console.print("\n[bold cyan]⚙️  Current Settings:[/bold cyan]")
        budget_display = f"₹{CONFIG['budget']}" if CONFIG['budget'] else "Not set yet"
        console.print(f"  [bold]1[/bold] — Budget:         {budget_display}")
        console.print(f"  [bold]2[/bold] — Scan Interval:  Every {CONFIG['scan_interval_minutes']} mins")
        console.print(f"  [bold]3[/bold] — Back\n")
        console.print(f"[dim]  Order: {order_summary}[/dim]\n")

        choice = input("Edit which? (1-3): ").strip()

        if choice == "1":
            try:
                val = input(f"Budget ₹ [{CONFIG['budget'] if CONFIG['budget'] else 'Not set'}]: ").strip()
                if val:
                    CONFIG["budget"] = int(val)
                    console.print(f"[green]✅ Budget set to ₹{CONFIG['budget']}[/green]")
            except ValueError:
                console.print("[red]Invalid[/red]")
        elif choice == "2":
            try:
                val = input(f"Every X mins [{CONFIG['scan_interval_minutes']}]: ").strip()
                if val:
                    CONFIG["scan_interval_minutes"] = int(val)
                    console.print(f"[green]✅ Set to {CONFIG['scan_interval_minutes']} mins[/green]")
            except ValueError:
                console.print("[red]Invalid[/red]")
        elif choice == "3":
            break


# ══════════════════════════════════════════════════
# 🏠 MAIN MENU
# ══════════════════════════════════════════════════
def main():
    if not LIVE_FILE.exists() and not BASE_FILE.exists():
        console.print("[red]❌ No data file found! Run data_engine.py first.[/red]")
        return

    restaurants  = load_restaurants()
    total_offers = sum(len(r.get("offers", [])) for r in restaurants)
    data_source  = "🟢 LIVE (data_engine.py)" if LIVE_FILE.exists() else "🟡 BASE (restaurants_data.json)"
    order_summary = ", ".join(f"{q}× {c}" for c, q in CONFIG["cuisine_quantities"].items()) if CONFIG["cuisine_quantities"] else "Not set yet"

    budget_display = f"₹{CONFIG['budget']}" if CONFIG['budget'] else "Not set yet"
    console.print(Panel(
        f"[bold orange1]🍜 DEAL SCANNER[/bold orange1]\n\n"
        f"📍 Kompally, Hyderabad\n"
        f"📄 Data:          {data_source}\n"
        f"🏪 Restaurants:   {len(restaurants)}\n"
        f"🏷  Total offers:  {total_offers}\n"
        f"💰 Budget:        {budget_display}\n"
        f"🛒 Your order:    {order_summary}",
        border_style="orange1"
    ))

    while True:
        console.print("\n  [bold cyan]1[/bold cyan] — 🔍 Scan now")
        console.print("  [bold cyan]2[/bold cyan] — 🤖 Background monitor")
        console.print("  [bold cyan]3[/bold cyan] — 🛒 Set cuisines & quantities")
        console.print("  [bold cyan]4[/bold cyan] — ⚙️  Settings (budget, interval)")
        console.print("  [bold cyan]5[/bold cyan] — 👋 Exit\n")

        choice = input("Enter choice (1-5): ").strip()

        if choice == "1":
            no_budget   = CONFIG["budget"] is None
            no_cuisines = not CONFIG["cuisine_quantities"]

            if no_budget and no_cuisines:
                console.print("[yellow]⚠ Set budget and cuisines to scan! (Options 3 & 4)[/yellow]")
            elif no_budget:
                console.print("[yellow]⚠ Set budget to scan! (Option 4)[/yellow]")
            elif no_cuisines:
                console.print("[yellow]⚠ Set cuisines to scan! (Option 3)[/yellow]")
            else:
                run_quantity_scan()
                input("\nPress Enter to continue...")
        elif choice == "2":
            background_monitor()
            input("\nPress Enter to continue...")
        elif choice == "3":
            select_cuisine_quantities()
        elif choice == "4":
            edit_settings()
        elif choice == "5":
            console.print("[dim]👋 Bye! Happy eating![/dim]")
            break
        else:
            console.print("[red]Invalid choice.[/red]")


if __name__ == "__main__":
    main()
