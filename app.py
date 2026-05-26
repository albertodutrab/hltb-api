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

    html = response.text

    soup = BeautifulSoup(html, "html.parser")

    results = []

    # procura TODOS os links de jogos
    game_links = soup.find_all("a", href=True)

    for link in game_links:

        href = link.get("href", "")

        if "/game/" not in href:
            continue

        title = link.get_text(strip=True)

        if not title:
            continue

        if is_blocked(title):
            continue

        parent_text = link.parent.get_text(" ", strip=True)

        def extract_time(label):

            pattern = rf"{label}\s+([0-9½¼¾\.]+ Hours?)"

            match = re.search(
                pattern,
                parent_text,
                re.IGNORECASE
            )

            if match:
                return match.group(1)

            return None

        parsed = {
            "game_name": title,
            "main_story": extract_time("Main Story"),
            "main_extras": extract_time("Main + Extras"),
            "completionist": extract_time("Completionist"),
            "score": similarity_score(game, title)
        }

        results.append(parsed)

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
