from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import requests
import re

app = Flask(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

BLOCKED_TERMS = [
    "dlc",
    "bundle",
    "skin"
]

# ─────────────────────────────────────────────
# NORMALIZE
# ─────────────────────────────────────────────

def normalize(text):

    if not text:
        return ""

    text = text.lower().strip()

    text = re.sub(r'[^a-z0-9 ]', '', text)
    text = re.sub(r'\s+', ' ', text)

    return text

# ─────────────────────────────────────────────
# BLOCK FILTER
# ─────────────────────────────────────────────

def is_blocked(title):

    title = normalize(title)

    for term in BLOCKED_TERMS:
        if term in title:
            return True

    return False

# ─────────────────────────────────────────────
# LEVENSHTEIN
# ─────────────────────────────────────────────

def levenshtein(s1, s2):

    s1 = normalize(s1)
    s2 = normalize(s2)

    if len(s1) < len(s2):
        return levenshtein(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))

    for i, c1 in enumerate(s1):

        current_row = [i + 1]

        for j, c2 in enumerate(s2):

            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)

            current_row.append(
                min(insertions, deletions, substitutions)
            )

        previous_row = current_row

    return previous_row[-1]

# ─────────────────────────────────────────────
# SIMILARITY
# ─────────────────────────────────────────────

def similarity_score(query, candidate):

    query = normalize(query)
    candidate = normalize(candidate)

    if not query or not candidate:
        return 0

    distance = levenshtein(query, candidate)

    max_len = max(len(query), len(candidate), 1)

    return 1 - (distance / max_len)

# ─────────────────────────────────────────────
# SEARCH HLTB
# ─────────────────────────────────────────────

def search_hltb(game):

    url = f"https://howlongtobeat.com/?q={game}"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    cards = soup.select(".GameCard_search_list__IuP7A")

    results = []

    for card in cards:

        try:

            title_el = card.select_one("h2")

            if not title_el:
                continue

            title = title_el.text.strip()

            if is_blocked(title):
                continue

            times = card.select(".GameCard_search_list_tidbit__yJZWT")

            parsed = {
                "game_name": title,
                "main_story": None,
                "main_extras": None,
                "completionist": None
            }

            for t in times:

                label = t.text.lower()

                strong = t.find_next("strong")

                if not strong:
                    continue

                value = strong.text.strip()

                if "main story" in label:
                    parsed["main_story"] = value

                elif "main + extras" in label:
                    parsed["main_extras"] = value

                elif "completionist" in label:
                    parsed["completionist"] = value

            parsed["score"] = similarity_score(
                game,
                title
            )

            results.append(parsed)

        except Exception:
            continue

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results

# ─────────────────────────────────────────────
# HOME
# ─────────────────────────────────────────────

@app.route("/")
def home():

    return jsonify({
        "status": "ok",
        "message": "HLTB API server running"
    })

# ─────────────────────────────────────────────
# MAIN ENDPOINT
# ─────────────────────────────────────────────

@app.route("/hltb")
def hltb():

    game = request.args.get("game")

    if not game:
        return jsonify({
            "error": "Parâmetro game obrigatório"
        }), 400

    try:

        results = search_hltb(game)

        if not results:
            return jsonify({
                "error": "Nenhum resultado encontrado",
                "query": game
            }), 404

        best = results[0]

        return jsonify(best)

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# ─────────────────────────────────────────────
# DEBUG
# ─────────────────────────────────────────────

@app.route("/hltb/all")
def hltb_all():

    game = request.args.get("game")

    try:

        results = search_hltb(game)

        return jsonify({
            "query": game,
            "results": results
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
