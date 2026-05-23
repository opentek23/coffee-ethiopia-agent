"""
Agent prospection café Éthiopie
Scraping direct : Google + annuaires éthiopiens
Bibliothèques  : requests + beautifulsoup4 (100% gratuit, zéro clé)
Résultat       : data/companies_master.csv + data/companies_latest.csv
"""

import os, csv, json, hashlib, re, time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY  = os.environ["ANTHROPIC_API_KEY"]
RUN_NUM  = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
NOW      = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
DATA_DIR = "data"
MASTER   = f"{DATA_DIR}/companies_master.csv"
LATEST   = f"{DATA_DIR}/companies_latest.csv"
FIELDS   = ["company_name", "city", "email", "phone", "website", "first_seen"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── 8 batches de requêtes en rotation ────────────────────────────────────────
BATCHES = [
    ["Ethiopian coffee export company contact email phone",
     "Ethiopia coffee trading company Addis Ababa contact"],
    ["Sidama coffee company Ethiopia email phone",
     "Yirgacheffe coffee producer exporter Ethiopia contact"],
    ["Jimma coffee Ethiopia company phone email",
     "Kaffa coffee Ethiopia exporter contact details"],
    ["Ethiopian coffee farmers cooperative union contact email",
     "Oromia coffee cooperative Ethiopia phone"],
    ["coffee roaster Ethiopia company email contact",
     "specialty coffee Ethiopia roasting company phone"],
    ["coffee packaging supplier Ethiopia email contact",
     "Ethiopia coffee bag manufacturer phone"],
    ["Ethiopia coffee company directory yellowpages",
     "Addis Ababa coffee business directory email phone"],
    ["green coffee bean supplier Ethiopia email phone",
     "Ethiopia coffee wholesale exporter contact"],
]

# Sources directes à scraper
DIRECT_SOURCES = [
    "https://www.yellowpages.com.et/search?keyword=coffee",
    "https://www.addisbiz.com/search?q=coffee",
    "https://ethiopianbusinessdirectory.com/coffee",
    "https://www.biznet.et/search/coffee",
]

# ── Google scrape ─────────────────────────────────────────────────────────────
def google_search(query: str) -> str:
    try:
        q = requests.utils.quote(query)
        url = f"https://www.google.com/search?q={q}&num=10&hl=en"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        parts = []
        # Titres + snippets des résultats organiques
        for g in soup.select("div.g")[:10]:
            title = g.select_one("h3")
            snippet = g.select_one("div.VwiC3b") or g.select_one("span.aCOpRe")
            link = g.select_one("a")
            if title:
                parts.append(f"Titre: {title.get_text()}")
            if snippet:
                parts.append(f"Extrait: {snippet.get_text()}")
            if link and link.get("href","").startswith("http"):
                parts.append(f"URL: {link['href']}")
            parts.append("---")

        result = "\n".join(parts)
        print(f"  → Google : {len(soup.select('div.g'))} résultats")
        return result
    except Exception as e:
        print(f"  ⚠ Google : {e}")
        return ""

# ── Scrape annuaires directs ───────────────────────────────────────────────────
def scrape_directory(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        # Extraire tout le texte visible
        text = soup.get_text(separator="\n", strip=True)
        # Garder seulement les lignes utiles (email, phone, nom)
        lines = [l for l in text.splitlines() if len(l) > 5][:80]
        return "\n".join(lines)
    except Exception as e:
        print(f"  ⚠ Annuaire {url} : {e}")
        return ""

# ── Extraction Claude ─────────────────────────────────────────────────────────
PROMPT = """Voici des résultats de recherche sur les entreprises éthiopiennes du café.

{results}

Extrais TOUTES les entreprises éthiopiennes liées au café (producteurs, exportateurs,
coopératives, torréfacteurs, emballage café).

Réponds UNIQUEMENT avec du JSON valide entre <json> et </json> :

<json>
[
  {{
    "company_name": "Nom exact",
    "city": "Ville en Ethiopie ou vide",
    "email": "email ou vide",
    "phone": "+251... ou vide",
    "website": "https://... ou vide"
  }}
]
</json>

Ne jamais inventer — laisser vide si inconnu. Si rien trouvé : <json>[]</json>"""

def extract(results_text: str) -> list[dict]:
    if not results_text.strip():
        return []
    client = anthropic.Anthropic(api_key=API_KEY)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": PROMPT.format(
                results=results_text[:5000]
            )}],
        )
        text = resp.content[0].text
        match = re.search(r"<json>(.*?)</json>", text, re.DOTALL)
        if not match:
            return []
        return json.loads(match.group(1).strip())
    except Exception as e:
        print(f"  ⚠ Claude : {e}")
        return []

# ── CSV master ────────────────────────────────────────────────────────────────
def _key(name: str) -> str:
    return hashlib.md5(name.lower().strip().encode()).hexdigest()

def load_master() -> dict:
    if not os.path.exists(MASTER):
        return {}
    with open(MASTER, newline="", encoding="utf-8") as f:
        return {_key(r["company_name"]): r for r in csv.DictReader(f) if r.get("company_name")}

def merge(new_items: list[dict], master: dict) -> tuple[dict, int]:
    added = 0
    for c in new_items:
        name = c.get("company_name", "").strip()
        if not name:
            continue
        k = _key(name)
        if k not in master:
            master[k] = {f: c.get(f, "") for f in FIELDS[:-1]}
            master[k]["first_seen"] = NOW
            added += 1
        else:
            for f in ["city", "email", "phone", "website"]:
                if not master[k].get(f) and c.get(f):
                    master[k][f] = c[f]
    return master, added

def save(rows: list[dict], path: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    idx     = RUN_NUM % len(BATCHES)
    queries = BATCHES[idx]
    print(f"=== Run #{RUN_NUM} | {NOW} | Batch {idx} ===\n")

    all_found = []

    # 1. Google scraping
    for i, q in enumerate(queries, 1):
        print(f"[Google {i}/{len(queries)}] {q[:65]}...")
        results = google_search(q)
        if results.strip():
            found = extract(results)
            print(f"  → {len(found)} entreprise(s)")
            all_found.extend(found)
        time.sleep(3)

    # 2. Annuaires directs éthiopiens
    print(f"\n[Annuaires] Scraping {len(DIRECT_SOURCES)} sources...")
    for url in DIRECT_SOURCES:
        print(f"  {url[:60]}...")
        text = scrape_directory(url)
        if text.strip():
            found = extract(text)
            print(f"  → {len(found)} entreprise(s)")
            all_found.extend(found)
        time.sleep(2)

    # 3. Fusion et sauvegarde
    master = load_master()
    master, added = merge(all_found, master)
    rows = sorted(master.values(), key=lambda r: r.get("company_name", "").lower())
    save(rows, MASTER)
    save(rows, LATEST)

    print(f"\n  +{added} nouvelles | Total : {len(master)} entreprises")
    print("✅ Run terminé.")

if __name__ == "__main__":
    main()
