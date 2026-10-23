"""
CineMatch recommendation engine - pure Python (no numpy / scikit-learn).

Algorithms
----------
1. Popularity      : Bayesian weighted rating (IMDb style) - solves cold start.
2. Content-based   : TF-IDF vectors of genres, director, actors, plot words;
                     cosine similarity; rating predicted from the most
                     similar movies the user has already rated.
3. Collaborative   : Item-based CF with adjusted cosine similarity
                     (ratings centred on each user's mean) + significance
                     shrinkage; prediction = item mean + weighted deviations.
4. Hybrid          : weighted blend of CF and content. Weight of CF grows
                     with the number of ratings the user has given.

Also provides an offline evaluation (RMSE, MAE, Precision@K, Recall@K, NDCG@K).
"""
import math
import random
import re
from collections import defaultdict

STOPWORDS = set(
    """the and for with that this from his her their they them are was were has have had who whom
    into over after before when while where what which about against between through during under
    again more most other some such than then there these those very can will just also been being
    both each only own same too out off him she its our you your""".split()
)
TOKEN_RE = re.compile(r"[a-z]{3,}")


def tokenize(text):
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def clip(x, lo=1.0, hi=5.0):
    return max(lo, min(hi, x))


class Recommender:
    METHODS = ("hybrid", "cf", "content", "popular")
    HYBRID_C = 40.0     # alpha = n / (n + C): CF weight grows with the user's rating count
    HYBRID_BASE = 0.2   # share of the user/item bias baseline mixed in for stability (tuned on other CV seeds)

    def __init__(self, movies, ratings, shrink=5.0, prior=3.0):
        """movies : list of dicts (id, title, year, genres[list], director, actors, description)
        ratings: iterable of (user_id, movie_id, rating)"""
        self.movies = {m["id"]: m for m in movies}
        self.shrink = shrink
        self.prior = prior
        self.user_ratings = defaultdict(dict)
        self.item_ratings = defaultdict(dict)
        for u, i, r in ratings:
            if i in self.movies:
                self.user_ratings[u][i] = float(r)
                self.item_ratings[i][u] = float(r)
        total = sum(sum(d.values()) for d in self.user_ratings.values())
        self.n_ratings = sum(len(d) for d in self.user_ratings.values())
        self.global_mean = total / self.n_ratings if self.n_ratings else 3.0
        self.user_mean = {u: sum(d.values()) / len(d) for u, d in self.user_ratings.items() if d}
        self.item_mean = {i: sum(d.values()) / len(d) for i, d in self.item_ratings.items() if d}
        self._build_popularity()
        self._build_content()
        self._build_item_similarity()

    # ------------------------------------------------------------------ build
    def _build_popularity(self):
        c, m = self.global_mean, self.prior
        self.popularity = {}
        for i in self.movies:
            v = len(self.item_ratings.get(i, {}))
            r = self.item_mean.get(i, c)
            self.popularity[i] = (v / (v + m)) * r + (m / (v + m)) * c

    def _build_content(self):
        raw, df = {}, defaultdict(int)
        for i, m in self.movies.items():
            f = defaultdict(float)
            for g in m["genres"]:
                f["g:" + g.lower()] += 3.0
            for d in m["director"].split(","):
                if d.strip():
                    f["d:" + d.strip().lower()] += 2.0
            for a in m["actors"].split(","):
                if a.strip():
                    f["a:" + a.strip().lower()] += 1.0
            for t in tokenize(m["description"]):
                f["w:" + t] += 1.0
            f["y:%d" % (m["year"] // 10 * 10)] += 0.5
            raw[i] = f
            for k in f:
                df[k] += 1
        n = len(raw)
        self.content_vec = {}
        for i, f in raw.items():
            v = {k: tf * (math.log((n + 1) / (df[k] + 1)) + 1.0) for k, tf in f.items()}
            norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
            self.content_vec[i] = {k: x / norm for k, x in v.items()}
        self._csim = {}

    def _build_item_similarity(self):
        num, sqi, sqj, cnt = defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(int)
        for u, items in self.user_ratings.items():
            mu = self.user_mean[u]
            centred = sorted((i, r - mu) for i, r in items.items())
            for a in range(len(centred)):
                i, ci = centred[a]
                for b in range(a + 1, len(centred)):
                    j, cj = centred[b]
                    key = (i, j)
                    num[key] += ci * cj
                    sqi[key] += ci * ci
                    sqj[key] += cj * cj
                    cnt[key] += 1
        self.cf_sim = defaultdict(dict)
        for (i, j), n in num.items():
            den = math.sqrt(sqi[(i, j)] * sqj[(i, j)])
            if den <= 0:
                continue
            s = (n / den) * (cnt[(i, j)] / (cnt[(i, j)] + self.shrink))
            self.cf_sim[i][j] = s
            self.cf_sim[j][i] = s

    # ------------------------------------------------------------- similarity
    def content_sim(self, i, j):
        key = (i, j) if i < j else (j, i)
        if key not in self._csim:
            a, b = self.content_vec[i], self.content_vec[j]
            if len(a) > len(b):
                a, b = b, a
            self._csim[key] = sum(v * b.get(k, 0.0) for k, v in a.items())
        return self._csim[key]

    def similar_items(self, movie_id, n=6):
        """Item-to-item similarity: 60% content + 40% collaborative."""
        if movie_id not in self.movies:
            return []
        scored = []
        for j in self.movies:
            if j == movie_id:
                continue
            s = 0.6 * self.content_sim(movie_id, j) + 0.4 * max(0.0, self.cf_sim.get(movie_id, {}).get(j, 0.0))
            scored.append((s, j))
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [(self.movies[j], round(s, 3)) for s, j in scored[:n]]

    # ------------------------------------------------------------ predictions
    def baseline(self, u, i):
        bu = self.user_mean.get(u, self.global_mean) - self.global_mean
        bi = self.item_mean.get(i, self.global_mean) - self.global_mean
        return clip(self.global_mean + bu + bi)

    def predict_cf(self, u, i, k=25):
        ur = self.user_ratings.get(u)
        if not ur:
            return None
        cands = [(s, j) for j, s in self.cf_sim.get(i, {}).items() if j in ur and s > 0]
        if not cands:
            return None
        cands.sort(reverse=True)
        cands = cands[:k]
        den = sum(s for s, _ in cands)
        dev = sum(s * (ur[j] - self.item_mean[j]) for s, j in cands)
        return clip(self.item_mean.get(i, self.global_mean) + dev / den)

    def predict_content(self, u, i, k=10):
        ur = self.user_ratings.get(u)
        if not ur:
            return None
        sims = [(self.content_sim(i, j), j) for j in ur if j != i]
        sims = [(s, j) for s, j in sims if s > 0]
        if not sims:
            return None
        sims.sort(reverse=True)
        sims = sims[:k]
        return clip(sum(s * ur[j] for s, j in sims) / sum(s for s, _ in sims))

    def _hybrid(self, u, i):
        n = len(self.user_ratings.get(u, {}))
        cf, cn = self.predict_cf(u, i), self.predict_content(u, i)
        a = n / (n + self.HYBRID_C)
        if cf is not None and cn is not None:
            mix = a * cf + (1 - a) * cn
        elif cf is not None:
            mix = cf
        elif cn is not None:
            mix = cn
        else:
            return self.baseline(u, i), False
        w = self.HYBRID_BASE
        return clip((1 - w) * mix + w * self.baseline(u, i)), True

    def predict(self, u, i, method="hybrid"):
        """Return (predicted_rating, covered). covered=False means a fallback was used."""
        if method == "baseline":
            return self.baseline(u, i), True
        if method == "popular":
            return self.popularity.get(i, self.global_mean), True
        if method == "cf":
            p = self.predict_cf(u, i)
        elif method == "content":
            p = self.predict_content(u, i)
        else:
            return self._hybrid(u, i)
        return (p, True) if p is not None else (self.baseline(u, i), False)

    # --------------------------------------------------------- recommendation
    def _explain(self, u, i):
        best, best_s = None, 0.05
        for j, r in self.user_ratings.get(u, {}).items():
            if r < 4 or j == i:
                continue
            s = (0.5 * self.content_sim(i, j) + 0.5 * max(0.0, self.cf_sim.get(i, {}).get(j, 0.0))) * (r / 5.0)
            if s > best_s:
                best, best_s = j, s
        return best

    def popular(self, n=10, genre=None):
        ids = [i for i, m in self.movies.items() if not genre or genre in m["genres"]]
        ids.sort(key=lambda i: (-self.popularity[i], i))
        return [self.movies[i] for i in ids[:n]]

    def recommend(self, user_id, n=10, method="hybrid", genre=None, fav_genres=None):
        """Always returns up to n items (falls back to popularity for cold-start users)."""
        method = method if method in self.METHODS else "hybrid"
        fav = {g.lower() for g in (fav_genres or []) if g}
        rated = self.user_ratings.get(user_id, {})
        cold = len(rated) == 0
        if cold:
            method = "popular"
        cands = [m for i, m in self.movies.items() if i not in rated and (not genre or genre in m["genres"])]
        scored = []
        for m in cands:
            i = m["id"]
            s, covered = self.predict(user_id, i, method)
            if method in ("cf", "content") and not covered:
                s -= 0.01  # tiny penalty: real predictions first, fallback after
            if fav and len(rated) < 5:
                overlap = len(fav & {g.lower() for g in m["genres"]}) / max(1, len(m["genres"]))
                s += 0.5 * overlap
            scored.append((s, covered, m))
        scored.sort(key=lambda t: (-t[0], -self.popularity[t[2]["id"]], t[2]["id"]))
        out = []
        for s, covered, m in scored[:n]:
            reason = None
            if not cold and method != "popular" and covered:
                j = self._explain(user_id, m["id"])
                if j:
                    reason = "Because you liked " + self.movies[j]["title"]
            if not reason:
                if fav and fav & {g.lower() for g in m["genres"]}:
                    reason = "Matches your favourite genres"
                else:
                    reason = "Highly rated by the community"
            shown = clip(s)
            out.append({"movie": m, "score": round(shown, 2), "match": int(round((shown - 1) / 4 * 100)), "reason": reason})
        return out


# --------------------------------------------------------------- evaluation
LABELS = {
    "baseline": "Bias baseline",
    "popular": "Popularity",
    "content": "Content-based",
    "cf": "Item-based CF",
    "hybrid": "Hybrid (proposed)",
    "random": "Random",
}


def evaluate(movies, ratings, k=10, test_ratio=0.2, threshold=4, seed=42, repeats=5):
    """Repeated hold-out validation: run `repeats` random 80/20 splits and average the metrics."""
    runs = [_evaluate_once(movies, ratings, k, test_ratio, threshold, seed + r) for r in range(repeats)]
    out = {"k": k, "repeats": repeats, "n_train": runs[0]["n_train"], "n_test": runs[0]["n_test"],
           "rating": [], "ranking": []}
    for table in ("rating", "ranking"):
        for idx, row in enumerate(runs[0][table]):
            avg = dict(row)
            for key, val in row.items():
                if isinstance(val, float):
                    avg[key] = sum(run[table][idx][key] for run in runs) / repeats
            out[table].append(avg)
    return out


def _evaluate_once(movies, ratings, k, test_ratio, threshold, seed):
    """One split: hold out ~20% of every user's ratings, train on the rest and measure
    rating-prediction error (RMSE/MAE) and top-K ranking quality."""
    rng = random.Random(seed)
    by_user = defaultdict(list)
    for r in ratings:
        by_user[r[0]].append(tuple(r))
    train, test = [], []
    for u in sorted(by_user):
        items = sorted(by_user[u])
        rng.shuffle(items)
        if len(items) < 5:
            train.extend(items)
            continue
        cut = max(1, int(round(len(items) * test_ratio)))
        test.extend(items[:cut])
        train.extend(items[cut:])
    model = Recommender(movies, train)
    out = {"k": k, "n_train": len(train), "n_test": len(test), "rating": [], "ranking": []}

    for m in ("baseline", "popular", "content", "cf", "hybrid"):
        se = ae = 0.0
        covered = 0
        for u, i, r in test:
            p, ok = model.predict(u, i, m)
            se += (p - r) ** 2
            ae += abs(p - r)
            covered += 1 if ok else 0
        n = max(1, len(test))
        out["rating"].append({"method": m, "label": LABELS[m], "rmse": math.sqrt(se / n),
                              "mae": ae / n, "coverage": covered / n})

    test_by_user = defaultdict(list)
    for u, i, r in test:
        test_by_user[u].append((i, r))
    all_ids = sorted(model.movies)
    for m in ("random", "popular", "content", "cf", "hybrid"):
        P = R = N = 0.0
        users = 0
        seen_items = set()
        for u in sorted(test_by_user):
            relevant = {i for i, r in test_by_user[u] if r >= threshold}
            if not relevant:
                continue
            rated = model.user_ratings.get(u, {})
            cands = [i for i in all_ids if i not in rated]
            if m == "random":
                order = cands[:]
                rng.shuffle(order)
            else:
                order = sorted(cands, key=lambda i: -model.predict(u, i, m)[0])
            top = order[:k]
            seen_items.update(top)
            hits = [1 if i in relevant else 0 for i in top]
            P += sum(hits) / k
            R += sum(hits) / len(relevant)
            dcg = sum(h / math.log2(p + 2) for p, h in enumerate(hits))
            idcg = sum(1 / math.log2(p + 2) for p in range(min(len(relevant), k)))
            N += dcg / idcg if idcg else 0
            users += 1
        users = max(1, users)
        out["ranking"].append({"method": m, "label": LABELS[m], "precision": P / users, "recall": R / users,
                               "ndcg": N / users, "coverage": len(seen_items) / max(1, len(all_ids))})
    return out