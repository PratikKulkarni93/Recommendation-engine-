"""CineMatch - Hybrid Movie Recommendation System (Flask + SQLite)."""
import os
import re
import secrets
import threading
import time
import zlib
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import database
from recommender import Recommender, evaluate
from seed_data import seed

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)


def load_secret_key():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = os.path.join(INSTANCE_DIR, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_secret_key(),
    DATABASE=os.environ.get("RECSYS_DB", os.path.join(INSTANCE_DIR, "recommender.db")),
    PER_PAGE=12,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
app.teardown_appcontext(database.close_db)
seed(app.config["DATABASE"])  # creates tables and demo data on first run

SIG_SQL = """SELECT (SELECT COUNT(*) FROM ratings), (SELECT COALESCE(SUM(rating),0) FROM ratings),
                    (SELECT COALESCE(MAX(updated_at),0) FROM ratings), (SELECT COUNT(*) FROM movies),
                    (SELECT COUNT(*) FROM users)"""


class ModelManager:
    """Keeps the trained recommender in memory and retrains when ratings change."""

    def __init__(self):
        self.lock = threading.Lock()
        self.sig = None
        self.model = None
        self.movies = []
        self.ratings = []
        self.genres = []
        self.n_users = 0
        self._eval = {}

    @staticmethod
    def _movie(row):
        genres = row["genres"].split("|")
        return {
            "id": row["id"], "title": row["title"], "year": row["year"], "genres": genres,
            "director": row["director"], "actors": row["actors"], "description": row["description"],
            "hue1": zlib.crc32(genres[0].encode()) % 360,
            "hue2": (zlib.crc32(row["title"].encode()) % 60 + zlib.crc32(genres[-1].encode()) % 300) % 360,
        }

    def get(self, db):
        sig = tuple(db.execute(SIG_SQL).fetchone())
        if sig != self.sig:
            with self.lock:
                if sig != self.sig:
                    self.movies = [self._movie(r) for r in db.execute("SELECT * FROM movies ORDER BY id")]
                    self.ratings = [tuple(r) for r in db.execute("SELECT user_id, movie_id, rating FROM ratings")]
                    self.model = Recommender(self.movies, self.ratings)
                    self.genres = sorted({g for m in self.movies for g in m["genres"]})
                    self.n_users = sig[4]
                    self._eval = {}
                    self.sig = sig
        return self.model

    def evaluation(self, k):
        if k not in self._eval:
            self._eval[k] = evaluate(self.movies, self.ratings, k=k)
        return self._eval[k]


mm = ModelManager()


# ------------------------------------------------------------------ helpers
def model():
    return mm.get(database.get_db())


def view(m, mdl, uid=None):
    """Movie dict enriched with rating stats for templates."""
    v = dict(m)
    i = m["id"]
    v["votes"] = len(mdl.item_ratings.get(i, {}))
    v["avg"] = mdl.item_mean.get(i, 0.0)
    v["user_rating"] = int(mdl.user_ratings.get(uid, {}).get(i, 0)) if uid else 0
    return v


def fav_genres_of(user):
    return [x for x in (user["fav_genres"].split(",") if user else []) if x]


def safe_next(target):
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("index")


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if g.user is None:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return f(*a, **kw)

    return wrapper


@app.before_request
def load_user_and_check_csrf():
    g.user = None
    uid = session.get("user_id")
    if uid:
        g.user = database.get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if g.user is None:
            session.clear()
    if request.method == "POST":
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        token = session.get("csrf", "")
        if not token or not secrets.compare_digest(sent, token):
            abort(400, "Invalid or missing CSRF token. Reload the page and try again.")


@app.context_processor
def inject_globals():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return {"csrf_token": lambda: session["csrf"], "current_user": g.get("user")}


# ------------------------------------------------------------------- pages
@app.route("/")
def index():
    mdl = model()
    uid = g.user["id"] if g.user else None
    top = [view(m, mdl, uid) for m in mdl.popular(8)]
    recs = []
    if g.user:
        for r in mdl.recommend(uid, 8, "hybrid", fav_genres=fav_genres_of(g.user)):
            r["movie"] = view(r["movie"], mdl, uid)
            recs.append(r)
    stats = {"movies": len(mdl.movies), "users": mm.n_users, "ratings": mdl.n_ratings}
    return render_template("index.html", top=top, recs=recs, stats=stats, genres=mm.genres)


@app.route("/movies")
def browse():
    mdl = model()
    uid = g.user["id"] if g.user else None
    q = request.args.get("q", "").strip()[:60]
    genre = request.args.get("genre", "")
    sort = request.args.get("sort", "popular")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    items = [view(m, mdl, uid) for m in mdl.movies.values()]
    if q:
        ql = q.lower()
        items = [m for m in items if ql in m["title"].lower() or ql in m["director"].lower() or ql in m["actors"].lower()]
    if genre:
        items = [m for m in items if genre in m["genres"]]
    keys = {
        "popular": lambda m: -mdl.popularity[m["id"]],
        "rating": lambda m: -m["avg"],
        "year": lambda m: -m["year"],
        "title": lambda m: m["title"].lower(),
    }
    items.sort(key=keys.get(sort, keys["popular"]))
    per = app.config["PER_PAGE"]
    pages = max(1, -(-len(items) // per))
    page = min(page, pages)
    return render_template("browse.html", items=items[(page - 1) * per: page * per], total=len(items),
                           q=q, genre=genre, sort=sort, page=page, pages=pages, genres=mm.genres)


@app.route("/movie/<int:movie_id>")
def movie_detail(movie_id):
    mdl = model()
    if movie_id not in mdl.movies:
        abort(404)
    uid = g.user["id"] if g.user else None
    m = view(mdl.movies[movie_id], mdl, uid)
    similar = [view(s, mdl, uid) for s, _ in mdl.similar_items(movie_id, 6)]
    hist = [0] * 5
    for r in mdl.item_ratings.get(movie_id, {}).values():
        hist[int(r) - 1] += 1
    predicted = None
    if uid and not m["user_rating"] and mdl.user_ratings.get(uid):
        predicted = round(mdl.predict(uid, movie_id, "hybrid")[0], 1)
    return render_template("movie.html", m=m, similar=similar, hist=hist, hist_max=max(hist) or 1, predicted=predicted)


@app.route("/recommendations")
@login_required
def recommendations():
    mdl = model()
    uid = g.user["id"]
    method = request.args.get("method", "hybrid")
    if method not in Recommender.METHODS:
        method = "hybrid"
    genre = request.args.get("genre", "")
    if genre not in mm.genres:
        genre = ""
    recs = mdl.recommend(uid, 12, method, genre or None, fav_genres_of(g.user))
    for r in recs:
        r["movie"] = view(r["movie"], mdl, uid)
    n_rated = len(mdl.user_ratings.get(uid, {}))
    return render_template("recommendations.html", recs=recs, method=method, genre=genre,
                           genres=mm.genres, n_rated=n_rated)


@app.route("/profile")
@login_required
def profile():
    mdl = model()
    uid = g.user["id"]
    rated = sorted(mdl.user_ratings.get(uid, {}).items(), key=lambda t: (-t[1], mdl.movies[t[0]]["title"]))
    items = [view(mdl.movies[i], mdl, uid) for i, _ in rated]
    by_genre = {}
    for i, r in rated:
        for gname in mdl.movies[i]["genres"]:
            by_genre.setdefault(gname, []).append(r)
    breakdown = sorted(((k, len(v), sum(v) / len(v)) for k, v in by_genre.items()), key=lambda t: (-t[1], t[0]))[:8]
    avg = sum(r for _, r in rated) / len(rated) if rated else 0
    return render_template("profile.html", items=items, breakdown=breakdown, avg=avg,
                           genres=mm.genres, favs=fav_genres_of(g.user))


@app.route("/profile/genres", methods=["POST"])
@login_required
def update_genres():
    chosen = [x for x in request.form.getlist("genres") if x in mm.genres][:6]
    db = database.get_db()
    db.execute("UPDATE users SET fav_genres = ? WHERE id = ?", (",".join(chosen), g.user["id"]))
    db.commit()
    flash("Favourite genres updated.", "success")
    return redirect(url_for("profile"))


@app.route("/evaluation")
def evaluation():
    model()
    try:
        k = int(request.args.get("k", 10))
    except ValueError:
        k = 10
    k = k if k in (5, 10, 15) else 10
    return render_template("evaluation.html", ev=mm.evaluation(k), k=k)


@app.route("/about")
def about():
    return render_template("about.html")


# -------------------------------------------------------------------- auth
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


@app.route("/register", methods=["GET", "POST"])
def register():
    model()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        chosen = [x for x in request.form.getlist("genres") if x in mm.genres][:6]
        error = None
        if not USERNAME_RE.match(username):
            error = "Username must be 3-20 characters: letters, numbers or underscore."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        db = database.get_db()
        if not error and db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            error = "That username is already taken."
        if error:
            flash(error, "error")
            return render_template("register.html", genres=mm.genres, chosen=chosen, username=username), 400
        cur = db.execute("INSERT INTO users(username, password_hash, fav_genres) VALUES (?,?,?)",
                         (username, generate_password_hash(password, method="pbkdf2:sha256"), ",".join(chosen)))
        db.commit()
        session.clear()
        session["user_id"] = cur.lastrowid
        flash("Welcome to CineMatch! Rate a few movies to get personalised picks.", "success")
        return redirect(url_for("browse"))
    return render_template("register.html", genres=mm.genres, chosen=[], username="")


@app.route("/login", methods=["GET", "POST"])
def login():
    nxt = request.values.get("next", "")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        user = database.get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            flash("Signed in as %s." % user["username"], "success")
            return redirect(safe_next(nxt))
        flash("Invalid username or password.", "error")
        return render_template("login.html", next=nxt, username=username), 401
    return render_template("login.html", next=nxt, username="")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("index"))


# --------------------------------------------------------------------- API
@app.route("/api/rate", methods=["POST"])
def api_rate():
    if g.user is None:
        return jsonify(ok=False, error="Please sign in to rate movies."), 401
    data = request.get_json(silent=True) or {}
    try:
        movie_id, rating = int(data.get("movie_id")), int(data.get("rating"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Invalid request."), 400
    if rating < 0 or rating > 5:
        return jsonify(ok=False, error="Rating must be between 1 and 5."), 400
    db = database.get_db()
    if not db.execute("SELECT 1 FROM movies WHERE id = ?", (movie_id,)).fetchone():
        return jsonify(ok=False, error="Movie not found."), 404
    if rating == 0:
        db.execute("DELETE FROM ratings WHERE user_id = ? AND movie_id = ?", (g.user["id"], movie_id))
    else:
        db.execute(
            """INSERT INTO ratings(user_id, movie_id, rating, updated_at) VALUES (?,?,?,?)
               ON CONFLICT(user_id, movie_id) DO UPDATE SET rating = excluded.rating, updated_at = excluded.updated_at""",
            (g.user["id"], movie_id, rating, time.time()),
        )
    db.commit()
    mdl = model()
    return jsonify(ok=True, rating=rating, avg=round(mdl.item_mean.get(movie_id, 0.0), 2),
                   votes=len(mdl.item_ratings.get(movie_id, {})), my_ratings=len(mdl.user_ratings.get(g.user["id"], {})))


@app.route("/api/recommendations")
@login_required
def api_recommendations():
    mdl = model()
    method = request.args.get("method", "hybrid")
    try:
        limit = max(1, min(30, int(request.args.get("limit", 10))))
    except ValueError:
        limit = 10
    recs = mdl.recommend(g.user["id"], limit, method, fav_genres=fav_genres_of(g.user))
    return jsonify(method=method, results=[
        {"id": r["movie"]["id"], "title": r["movie"]["title"], "year": r["movie"]["year"],
         "genres": r["movie"]["genres"], "predicted_rating": r["score"], "match": r["match"], "reason": r["reason"]}
        for r in recs])


@app.route("/api/movies/<int:movie_id>/similar")
def api_similar(movie_id):
    mdl = model()
    if movie_id not in mdl.movies:
        return jsonify(error="Movie not found"), 404
    return jsonify(results=[{"id": m["id"], "title": m["title"], "similarity": s} for m, s in mdl.similar_items(movie_id, 10)])


# ---------------------------------------------------------------- errors
@app.errorhandler(400)
def bad_request(e):
    return render_template("error.html", code=400, message=getattr(e, "description", "Bad request")), 400


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="The page you are looking for does not exist."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Something went wrong on our side."), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")