from flask import Flask, request, jsonify
from howlongtobeatpy import HowLongToBeat
import re

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────
# Termos proibidos
# ─────────────────────────────────────────────────────────────

BLOCKED_TERMS = [
    "dlc",
    "bundle",
    "skin"
]

# ─────────────────────────────────────────────────────────────
# Limpeza de texto
# ─────────────────────────────────────────────────────────────

def normalize(text):
    if not text:
        return ""

    text = text.lower().strip()

    # remove caracteres especiais
    text = re.sub(r'[^a-z0-9 ]', '', text)

    # remove espaços duplicados
    text = re.sub(r'\s+', ' ', text)

    return text


# ─────────────────────────────────────────────────────────────
# Verificar se deve excluir
# ─────────────────────────────────────────────────────────────

def is_blocked(title):
    normalized = normalize(title)

    for term in BLOCKED_TERMS:
        if term in normalized:
            return True

    return False


# ─────────────────────────────────────────────────────────────
# Distância Levenshtein
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# Similaridade
# ─────────────────────────────────────────────────────────────

def similarity_score(query, candidate):
    query = normalize(query)
    candidate = normalize(candidate)

    if not query or not candidate:
        return 0

    distance = levenshtein(query, candidate)

    max_len = max(len(query), len(candidate), 1)

    return 1 - (distance / max_len)


# ─────────────────────────────────────────────────────────────
# Escolher melhor resultado
# ─────────────────────────────────────────────────────────────

def choose_best_match(query, results):
    valid_results = []

    for r in results:
        try:
            if not r or not r.game_name:
                continue

            # Ignora DLCs, bundles e skins
            if is_blocked(r.game_name):
                continue

            score = similarity_score(query, r.game_name)

            valid_results.append({
                "obj": r,
                "score": score
            })

        except Exception:
            continue

    if not valid_results:
        return None

    valid_results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return valid_results[0]


# ─────────────────────────────────────────────────────────────
# Home
# ─────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "message": "HLTB API server running"
    })


# ─────────────────────────────────────────────────────────────
# Melhor resultado
# ─────────────────────────────────────────────────────────────

@app.route("/hltb")
def hltb():
    game = request.args.get("game")

    if not game:
        return jsonify({
            "error": "Parâmetro 'game' é obrigatório"
        }), 400

    try:
        results = HowLongToBeat().search(game)

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

        game_data = best["obj"]

        return jsonify({
            "query": game,
            "matched_game": game_data.game_name,
            "similarity_score": round(best["score"], 3),

            "main_story": game_data.main_story,
            "main_extras": game_data.main_extra,
            "completionist": game_data.completionist
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


# ─────────────────────────────────────────────────────────────
# Debug - listar candidatos
# ─────────────────────────────────────────────────────────────

@app.route("/hltb/all")
def hltb_all():
    game = request.args.get("game")

    if not game:
        return jsonify({
            "error": "Parâmetro 'game' é obrigatório"
        }), 400

    try:
        results = HowLongToBeat().search(game)

        if not results:
            return jsonify({
                "error": "Nenhum resultado encontrado",
                "query": game
            }), 404

        output = []

        for r in results:
            try:
                if not r or not r.game_name:
                    continue

                blocked = is_blocked(r.game_name)

                output.append({
                    "game_name": r.game_name,
                    "blocked": blocked,
                    "similarity_score": round(
                        similarity_score(game, r.game_name),
                        3
                    ),
                    "main_story": r.main_story,
                    "main_extras": r.main_extra,
                    "completionist": r.completionist
                })

            except Exception:
                continue

        output.sort(
            key=lambda x: x["similarity_score"],
            reverse=True
        )

        return jsonify({
            "query": game,
            "results": output
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
