from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import json
import re
import hashlib
import time

app = Flask(__name__)
CORS(app)

# ── Similaridade de strings (Levenshtein) ──────────────────────────────────────

def levenshtein(s1, s2):
    s1, s2 = s1.lower(), s2.lower()
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[len(s2)]

def similarity_score(query, candidate):
    """Retorna score de 0 a 1 (1 = idêntico)."""
    query     = re.sub(r'[^a-z0-9 ]', '', query.lower().strip())
    candidate = re.sub(r'[^a-z0-9 ]', '', candidate.lower().strip())
    dist = levenshtein(query, candidate)
    max_len = max(len(query), len(candidate), 1)
    return 1 - dist / max_len

def best_match(query, candidates):
    """Escolhe o candidato mais similar ao query."""
    scored = [(c, similarity_score(query, c.get('game_name', ''))) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0] if scored else None

# ── HowLongToBeat scraper ──────────────────────────────────────────────────────

HLTB_SEARCH_URL = "https://howlongtobeat.com/api/search"
HLTB_BASE_URL   = "https://howlongtobeat.com"

def get_hltb_headers():
    return {
        "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer":      "https://howlongtobeat.com/",
        "Origin":       "https://howlongtobeat.com",
        "Content-Type": "application/json",
        "Accept":       "*/*",
    }

def build_search_payload(game_name):
    return {
        "searchType":    "games",
        "searchTerms":   game_name.split(),
        "searchPage":    1,
        "size":          10,
        "searchOptions": {
            "games": {
                "userId":      0,
                "platform":    "",
                "sortCategory": "popular",
                "rangeCategory": "main",
                "rangeTime":   {"min": None, "max": None},
                "gameplay":    {"perspective": "", "flow": "", "genre": "", "subGenre": ""},
                "rangeYear":   {"min": "", "max": ""},
                "modifier":    "",
            },
            "users":  {"sortCategory": "postcount"},
            "lists":  {"sortCategory": "follows"},
            "filter": "",
            "sort":   0,
            "randomizer": 0,
        },
        "useCache": True,
    }

def seconds_to_hours(seconds):
    if not seconds:
        return None
    hours = seconds / 3600
    return round(hours, 1)

def search_hltb(game_name):
    payload = build_search_payload(game_name)
    try:
        resp = requests.post(
            HLTB_SEARCH_URL,
            headers=get_hltb_headers(),
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        print(f"Erro na busca HLTB: {e}")
        return []

def parse_game(game):
    return {
        "game_name":      game.get("game_name", ""),
        "main_story":     seconds_to_hours(game.get("comp_main")),
        "main_extras":    seconds_to_hours(game.get("comp_plus")),
        "completionist":  seconds_to_hours(game.get("comp_100")),
        "hltb_id":        game.get("game_id"),
        "image_url":      f"{HLTB_BASE_URL}{game.get('game_image', '')}",
    }

# ── Rotas ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({"status": "ok", "message": "HLTB API server running"})

@app.route("/hltb")
def hltb():
    game_name = request.args.get("game", "").strip()
    if not game_name:
        return jsonify({"error": "Parâmetro 'game' é obrigatório"}), 400

    results = search_hltb(game_name)
    if not results:
        return jsonify({"error": "Nenhum resultado encontrado", "query": game_name}), 404

    # Escolhe o resultado mais similar ao nome buscado
    best = best_match(game_name, results)
    if not best:
        return jsonify({"error": "Não foi possível determinar o melhor resultado"}), 404

    return jsonify(parse_game(best))

@app.route("/hltb/all")
def hltb_all():
    """Retorna os top-5 resultados com score de similaridade (útil para debug)."""
    game_name = request.args.get("game", "").strip()
    if not game_name:
        return jsonify({"error": "Parâmetro 'game' é obrigatório"}), 400

    results = search_hltb(game_name)
    parsed  = [parse_game(g) for g in results[:5]]
    for p, r in zip(parsed, results[:5]):
        p["similarity"] = round(similarity_score(game_name, r.get("game_name", "")), 3)
    parsed.sort(key=lambda x: x["similarity"], reverse=True)
    return jsonify(parsed)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
