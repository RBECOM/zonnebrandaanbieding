#!/usr/bin/env python3
"""Build a conservative sunscreen selection from the Plein Daisycon feed."""

import argparse
import csv
import html
import json
import os
import re
import sys
import urllib.request
from urllib.parse import quote
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo


DIRECT_CATEGORIES = {"zonnebrandolie", "zon"}
EXCLUDE = re.compile(r"after\s*sun|zelfbruin|self.?tan|bruinings|tan accelerator|huisdier|hond|haar", re.I)
SUN_TERMS = re.compile(r"zonnebrand|zonnecr[eè]me|sun\s*(?:cream|lotion|spray|fluid|stick)|suncare|solaire|anthelios", re.I)
PROMO = re.compile(r"^(\d+)\s*\+\s*(\d+)\s*gratis:|^2e\s+halve\s+prijs:", re.I)
PACK = re.compile(r"^\s*(\d+)\s*x\s+", re.I)
SPF = re.compile(r"\bSPF\s*([0-9]{1,2})(\+)?", re.I)
AMOUNT = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*(ml|gr|g)\b", re.I)


def number(value, default=0.0):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def round_money(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fetch_rows(source):
    if source.startswith(("https://", "http://")):
        request = urllib.request.Request(source, headers={"User-Agent": "zonnebrandaanbieding-feed/1.0"})
        handle = urllib.request.urlopen(request, timeout=180)
        text = (line.decode("utf-8-sig") for line in handle)
        return csv.DictReader(text, delimiter=";")
    handle = open(source, encoding="utf-8-sig", newline="")
    return csv.DictReader(handle, delimiter=";")


def normalize(row):
    title = (row.get("title") or "").strip()
    category = (row.get("category") or "").strip()
    text = f"{title} {category} {row.get('description', '')}"
    if (row.get("in_stock") or "").lower() != "true":
        return None
    if not row.get("image_default") or not row.get("link"):
        return None
    if EXCLUDE.search(title):
        return None
    if category.lower() not in DIRECT_CATEGORIES and not SUN_TERMS.search(title):
        return None

    spf_match = SPF.search(title)
    spf = int(spf_match.group(1)) if spf_match else None
    if not spf or spf < 15:
        return None

    price = number(row.get("price"))
    if price <= 0:
        return None
    old_price = number(row.get("price_old"))
    discount = int(round(number(row.get("discount_percentage"))))
    promo_match = PROMO.search(title)
    promo = promo_match.group(0).rstrip(":") if promo_match else ""

    pack_match = PACK.search(title)
    pack_count = int(pack_match.group(1)) if pack_match else 1
    size_text = (row.get("size") or "").strip()
    amount_match = AMOUNT.search(size_text)
    unit_ml = number(amount_match.group(1)) if amount_match else None
    unit_label = amount_match.group(2).lower() if amount_match else None
    if unit_label == "g":
        unit_label = "gr"
    total_ml = unit_ml * pack_count if unit_ml else None
    reliable_unit_price = bool(total_ml and not promo)
    price_per_100ml = round(price / total_ml * 100, 2) if reliable_unit_price else None

    offer_quantity = pack_count
    offer_total = price
    effective_each = price / pack_count
    if promo_match:
        promo_lower = promo.lower()
        free_match = re.match(r"(\d+)\s*\+\s*(\d+)\s*gratis", promo_lower)
        if free_match:
            paid, free = map(int, free_match.groups())
            offer_quantity = paid + free
            offer_total = price * paid
            effective_each = offer_total / offer_quantity
        elif promo_lower.startswith("2e halve prijs"):
            offer_quantity = 2
            offer_total = round_money(price * 1.5)
            effective_each = offer_total / 2
    offer_total_ml = unit_ml * offer_quantity if unit_ml else None
    effective_price_per_100ml = (
        round(offer_total / offer_total_ml * 100, 2) if offer_total_ml else price_per_100ml
    )

    lowered = title.lower()
    if re.search(r"kids?|baby|kind", lowered):
        use_case = "kinderen"
    elif re.search(r"gezicht|face|fluid|flu[iï]de|anti-shine", lowered):
        use_case = "gezicht"
    elif re.search(r"stick|lip", lowered):
        use_case = "onderweg"
    else:
        use_case = "lichaam"

    if re.search(r"stick|lip", lowered):
        product_form = "stick"
    elif re.search(r"spray|mist|spuitbus", lowered):
        product_form = "spray"
    elif re.search(r"fluid|flu[iï]de", lowered):
        product_form = "fluid"
    elif re.search(r"olie|oil", lowered):
        product_form = "olie"
    else:
        product_form = "crème/lotion"

    clean_title = re.sub(r"^(?:\d+\s*x\s+|\d+\s*\+\s*\d+\s*gratis:\s*|2e\s+halve\s+prijs:\s*)", "", title, flags=re.I)
    return {
        "sku": row.get("sku", ""),
        "ean": row.get("ean", ""),
        "brand": row.get("brand", ""),
        "title": clean_title,
        "full_title": title,
        "category": category,
        "use_case": use_case,
        "product_form": product_form,
        "spf": spf,
        "spf_plus": bool(spf_match and spf_match.group(2)),
        "price": round(price, 2),
        "old_price": round(old_price, 2) if old_price > price else None,
        "discount_percentage": discount if discount > 0 else None,
        "promotion": promo or None,
        "pack_count": pack_count,
        "unit_ml": unit_ml,
        "unit_label": unit_label,
        "total_ml": total_ml,
        "price_per_100ml": price_per_100ml,
        "offer_quantity": offer_quantity,
        "offer_total": round_money(offer_total),
        "effective_each": round_money(effective_each),
        "offer_total_ml": offer_total_ml,
        "effective_price_per_100ml": effective_price_per_100ml,
        "shipping": number(row.get("price_shipping"), None),
        "image": row.get("image_default") or row.get("image_small"),
        "url": row.get("link"),
    }


def deduplicate(products):
    # Keep one listing per EAN/use case. Prefer a real discount, then the lowest reliable unit price.
    grouped = defaultdict(list)
    for product in products:
        grouped[(product["ean"] or product["sku"], product["use_case"])].append(product)
    result = []
    for group in grouped.values():
        group.sort(key=lambda p: (
            -(p["discount_percentage"] or 0),
            p["price_per_100ml"] if p["price_per_100ml"] is not None else 999999,
            p["price"],
        ))
        result.append(group[0])
    return result


def choose(products):
    by_case = defaultdict(list)
    for product in products:
        by_case[product["use_case"]].append(product)

    def diverse(items, limit=8):
        """Prefer variety; fill remaining slots only after each brand had a turn."""
        chosen = []
        used_brands = set()
        for product in items:
            brand = product["brand"].strip().casefold()
            if brand and brand in used_brands:
                continue
            chosen.append(product)
            used_brands.add(brand)
            if len(chosen) == limit:
                return chosen
        for product in items:
            if product not in chosen:
                chosen.append(product)
            if len(chosen) == limit:
                break
        return chosen

    def value_items(case, limit=8, min_spf=30):
        items = [p for p in by_case[case] if p["spf"] >= min_spf and p["price_per_100ml"] is not None]
        items.sort(key=lambda p: (p["price_per_100ml"], p["price"]))
        return diverse(items, limit)

    deals = [p for p in products if p["spf"] >= 30 and (p["discount_percentage"] or p["promotion"])]
    deals.sort(key=lambda p: (
        -(p["discount_percentage"] or (50 if p["promotion"] else 0)),
        p["price_per_100ml"] if p["price_per_100ml"] is not None else 999999,
        p["price"],
    ))

    return {
        "deals": diverse(deals, 12),
        "lichaam": value_items("lichaam"),
        "kinderen": value_items("kinderen"),
        "gezicht": value_items("gezicht"),
        "onderweg": value_items("onderweg", min_spf=30),
    }


def money(value):
    return f"€ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tracked_url(url, page_id, placement, sku):
    """Add Daisycon Sub IDs without changing campaign, media or deeplink data."""
    values = {
        "ws": page_id[:100],
        "ws2": placement[:50],
        "ws3": str(sku or "onbekend")[:50],
    }
    tracked = url
    for parameter, value in values.items():
        encoded = quote(value, safe="-_.")
        pattern = rf"([?&]){parameter}=[^&]*"
        if re.search(pattern, tracked):
            tracked = re.sub(pattern, lambda match: f"{match.group(1)}{parameter}={encoded}", tracked, count=1)
        else:
            separator = "&" if "?" in tracked else "?"
            tracked += f"{separator}{parameter}={encoded}"
    return tracked


def product_card(product, page_id, placement):
    raw_title = product["title"] or product["full_title"]
    title = html.escape(raw_title)
    brand = html.escape(product["brand"] or "Plein.nl")
    product_form = html.escape(product["product_form"].capitalize())
    badge = product["promotion"] or (
        f"{product['discount_percentage']}% korting" if product["discount_percentage"] else f"SPF {product['spf']}"
    )
    main_price = money(product["effective_each"])
    unit_price = product["effective_price_per_100ml"]
    secondary = f'{money(unit_price)} per 100 ml' if unit_price is not None else "Prijs per 100 ml niet beschikbaar"
    if product["promotion"]:
        contents = f'{product["offer_quantity"]} × {product["unit_ml"]:g} {product["unit_label"]}' if product["unit_ml"] else f'{product["offer_quantity"]} stuks'
        offer = f'{contents} voor {money(product["offer_total"])}'
    elif product["pack_count"] > 1 and product["unit_ml"]:
        offer = f'{product["pack_count"]} × {product["unit_ml"]:g} {product["unit_label"]} voor {money(product["price"])}'
    elif product["old_price"]:
        offer = f'Van {money(product["old_price"])} voor {money(product["price"])}'
    else:
        offer = "&nbsp;"
    label = f'Bekijk {raw_title}'
    click_url = tracked_url(product["url"], page_id, placement, product["sku"])
    return (
        '<article class="feed-card">'
        f'<a class="feed-card-link" href="{html.escape(click_url, quote=True)}" rel="sponsored nofollow noopener" target="_blank" aria-label="{html.escape(label, quote=True)}"></a>'
        f'<span class="feed-label">{html.escape(badge)}</span>'
        f'<img src="{html.escape(product["image"], quote=True)}" alt="{title}" loading="lazy" width="320" height="240">'
        '<div class="feed-card-body">'
        f'<span class="feed-brand">{brand} - {product_form}</span><h3>{title}</h3>'
        f'<div class="feed-price-stack"><div class="feed-price"><strong>{main_price}</strong><span>per stuk</span></div>'
        f'<p class="feed-unit">{html.escape(secondary)}</p><p class="feed-offer">{offer}</p></div>'
        '<span class="feed-cta">Bekijk hier <span aria-hidden="true">→</span></span>'
        '</div></article>'
    )


def replace_region(path, name, products, more_href, more_label="Bekijk meer"):
    start = f"<!-- FEED:{name}:START -->"
    end = f"<!-- FEED:{name}:END -->"
    text = path.read_text(encoding="utf-8")
    if start not in text or end not in text:
        raise RuntimeError(f"Missing feed markers {name} in {path}")
    page_id = "homepage" if path.stem == "index" else path.stem
    cards = "\n".join(product_card(item, page_id, name.lower()) for item in products)
    more = f'<div class="feed-more"><a href="{html.escape(more_href, quote=True)}">{html.escape(more_label)} <span aria-hidden="true">→</span></a></div>'
    replacement = f'{start}\n<div class="feed-grid">\n{cards}\n</div>\n{more}\n{end}'
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    path.write_text(before + replacement + after, encoding="utf-8")


def replace_text_region(path, name, replacement):
    start = f"<!-- FEED:{name}:START -->"
    end = f"<!-- FEED:{name}:END -->"
    text = path.read_text(encoding="utf-8")
    if start not in text or end not in text:
        raise RuntimeError(f"Missing feed markers {name} in {path}")
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    path.write_text(before + start + replacement + end + after, encoding="utf-8")


def update_pages(root, selections, catalogue, updated_at):
    local_time = updated_at.astimezone(ZoneInfo("Europe/Amsterdam"))
    months = ("januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december")
    readable = f'{local_time.day} {months[local_time.month - 1]} {local_time.year} om {local_time:%H:%M}'
    freshness = f'<b>Laatst bijgewerkt:</b> <time datetime="{updated_at.isoformat()}">{readable}</time>'
    replace_text_region(root / "aanbiedingen.html", "UPDATED", freshness)
    replace_region(root / "index.html", "HOME", selections["deals"][:9], "aanbiedingen.html", "Bekijk alle aanbiedingen")
    replace_region(root / "zonnebrand-kinderen.html", "KINDEREN", selections["kinderen"][:6], "aanbiedingen.html?gebruik=kinderen", "Bekijk meer aanbiedingen")
    replace_region(root / "zonnebrand-gezicht.html", "GEZICHT", selections["gezicht"][:6], "aanbiedingen.html?gebruik=gezicht", "Bekijk meer aanbiedingen")
    replace_region(root / "spf-30-of-50.html", "SPF", selections["lichaam"][:6], "aanbiedingen.html", "Bekijk meer aanbiedingen")
    winter = [p for p in selections["gezicht"] + selections["onderweg"] if p["spf"] >= 50]
    replace_region(root / "zonnebrand-wintersport.html", "WINTERSPORT", diverse_products(winter, 6), "aanbiedingen.html?spf=50", "Bekijk meer aanbiedingen")
    replace_region(root / "aanbiedingen.html", "LISTING", catalogue[:24], "#filters", "Pas de filters aan")
    top_patterns = [
        "oil control dry touch gel-crème spf 50+ 50 ml", "oil control gel-creme spf 50+ 50 ml",
        "every day sun spf 50 spray 180 ml", "super uv over make-up mist spf 50+ 75 ml",
        "ideal bronze beschermende mist spf 30 150 ml", "sun pigment control spf 50+ 50 ml",
        "zonnecrème gezicht anti-shine spf 50 50 ml", "protect & bronze zonnebrand spf 30 200 ml",
        "ideal bronze beschermende melkspray", "6x hawaiian tropic luminosity zonnebrand lotion very high spf50+",
    ]
    top10 = []
    for pattern in top_patterns:
        matches = [p for p in catalogue if pattern.casefold() in p["full_title"].casefold()]
        if matches:
            singles = [p for p in matches if p["pack_count"] == 1]
            top10.append((singles or matches)[0])
    replace_region(root / "top-10-zonnebrand.html", "TOP10", top10[:10], "aanbiedingen.html", "Bekijk alle aanbiedingen")
    category_pages = {
        "zonnebrand-lichaam.html": ("LICHAAM", lambda p: p["use_case"] == "lichaam"),
        "zonnebrandspray.html": ("SPRAY", lambda p: p["product_form"] == "spray"),
        "zonnebrandstick.html": ("STICK", lambda p: p["product_form"] == "stick"),
        "zonnebrandfluid.html": ("FLUID", lambda p: p["product_form"] == "fluid"),
        "zonnebrandcreme-lotion.html": ("CREME", lambda p: p["product_form"] == "crème/lotion"),
        "zonnebrandolie.html": ("OLIE", lambda p: p["product_form"] == "olie"),
    }
    query_values = {"LICHAAM": "gebruik=lichaam", "SPRAY": "vorm=spray", "STICK": "vorm=stick", "FLUID": "vorm=fluid", "CREME": "vorm=crème%2Flotion", "OLIE": "vorm=olie"}
    for filename, (marker, predicate) in category_pages.items():
        items = [p for p in catalogue if predicate(p)]
        replace_region(root / filename, marker, items[:12], f"aanbiedingen.html?{query_values[marker]}", "Bekijk alle passende producten")


def diverse_products(items, limit):
    chosen, brands = [], set()
    for item in items:
        brand = item["brand"].strip().casefold()
        if brand in brands:
            continue
        chosen.append(item)
        brands.add(brand)
        if len(chosen) == limit:
            break
    return chosen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Local CSV path. Otherwise DAISYCON_FEED_URL is used.")
    parser.add_argument("--output", default="data/products.json")
    args = parser.parse_args()
    source = args.input or os.environ.get("DAISYCON_FEED_URL")
    if not source:
        sys.exit("Missing --input or DAISYCON_FEED_URL")

    products = []
    total_rows = 0
    for row in fetch_rows(source):
        total_rows += 1
        item = normalize(row)
        if item:
            products.append(item)
    products = deduplicate(products)
    selections = choose(products)
    if total_rows < 1000:
        sys.exit(f"Feed validation failed: only {total_rows} rows received")
    if len(products) < 50:
        sys.exit(f"Feed validation failed: only {len(products)} eligible sunscreen products")
    if len(selections["deals"]) < 3:
        sys.exit("Feed validation failed: fewer than 3 deal products")
    catalogue = sorted(products, key=lambda p: (
        not bool(p["promotion"] or p["discount_percentage"]),
        p["effective_price_per_100ml"] if p["effective_price_per_100ml"] is not None else 999999,
        p["effective_each"],
    ))
    updated_at = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "updated_at": updated_at.isoformat(),
        "source": "Plein.nl via Daisycon",
        "total_feed_products": total_rows,
        "eligible_sun_products": len(products),
        "shipping_note": "Bezorgkosten gelden per bestelling en kunnen afhangen van de winkelmand.",
        "selections": selections,
        "catalogue": catalogue,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_pages(Path(__file__).resolve().parents[1], selections, catalogue, updated_at)
    counts = ", ".join(f"{key}={len(value)}" for key, value in selections.items())
    print(f"Processed {total_rows} rows; eligible={len(products)}; {counts}")


if __name__ == "__main__":
    main()
