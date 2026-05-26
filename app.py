from flask import Flask, request, jsonify
from howlongtobeatpy import HowLongToBeat
import re

app = Flask(__name__)

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
# CHOOSE BEST MATCH
# ─────────────────────────────────────────────

def choose_best_match(query, results):

    valid = []

    for r in results:

        try:

            name = getattr(r, "game_name", None)

            if not name:
                continue

            if is_blocked(name):
                continue

            score = similarity_score(query, name)

            valid.append({
                "score": score,
                "data": r
            })

        except Exception:
            continue

    if not valid:
        return None

    valid.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return valid[0]

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

    try:
        results = HowLongToBeat().search(game) or []

    except Exception as internal_error:

        return jsonify({
            "error": f"Erro interno HLTB: {str(internal_error)}"
        }), 500

    if not results:
        return jsonify({
            "error": "Nenhum resultado encontrado",
            "query": game
        }), 404

    best = choose_best_match(game, results)

        if not best:
            return jsonify({
                "error": "Nenhum resultado válido encontrado",
                "query": game
            }), 404

        data = best["data"]

        return jsonify({
            "query": game,
            "matched_game": data.game_name,
            "similarity_score": round(best["score"], 3),

            "main_story": data.main_story,
            "main_extras": data.main_extra,
            "completionist": data.completionist
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
