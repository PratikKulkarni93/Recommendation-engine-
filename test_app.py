"""Automated tests. Run:  python test_app.py"""
import os
import re
import tempfile
import unittest

_tmp = tempfile.mkdtemp()
os.environ["RECSYS_DB"] = os.path.join(_tmp, "test.db")

import app as appmod  # noqa: E402
from recommender import Recommender  # noqa: E402


class CineMatchTests(unittest.TestCase):
    def setUp(self):
        appmod.app.config["TESTING"] = True
        self.c = appmod.app.test_client()

    def token(self, path="/login"):
        html = self.c.get(path).get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([0-9a-f]+)"', html).group(1)

    def login(self, user="demo", pw="demo123"):
        t = self.token()
        return self.c.post("/login", data={"username": user, "password": pw, "csrf_token": t}, follow_redirects=True)

    def test_public_pages(self):
        for url in ["/", "/movies", "/movies?q=nolan", "/movies?genre=Sci-Fi&sort=year&page=2", "/movies?page=abc",
                    "/movie/1", "/evaluation", "/evaluation?k=5", "/evaluation?k=zzz", "/about", "/login", "/register"]:
            self.assertEqual(self.c.get(url).status_code, 200, url)
        self.assertEqual(self.c.get("/movie/9999").status_code, 404)
        self.assertEqual(self.c.get("/nope").status_code, 404)

    def test_auth_required(self):
        self.assertEqual(self.c.get("/recommendations").status_code, 302)
        self.assertEqual(self.c.get("/profile").status_code, 302)
        self.assertEqual(self.c.get("/api/recommendations").status_code, 302)

    def test_csrf_blocks_post(self):
        self.assertEqual(self.c.post("/login", data={"username": "demo", "password": "demo123"}).status_code, 400)

    def test_login_flow_and_pages(self):
        r = self.login()
        self.assertIn("Signed in as demo", r.get_data(as_text=True))
        for m in ("hybrid", "cf", "content", "popular", "bogus"):
            resp = self.c.get("/recommendations?method=%s&genre=Drama" % m)
            self.assertEqual(resp.status_code, 200, m)
            self.assertIn("Recommended for you", resp.get_data(as_text=True))
        self.assertEqual(self.c.get("/profile").status_code, 200)
        self.assertEqual(self.c.get("/api/recommendations?limit=5").get_json()["results"].__len__(), 5)

    def test_bad_login(self):
        r = self.login("demo", "wrong")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Invalid username or password", r.get_data(as_text=True))

    def test_open_redirect_blocked(self):
        t = self.token()
        r = self.c.post("/login", data={"username": "demo", "password": "demo123", "csrf_token": t, "next": "//evil.com"})
        self.assertEqual(r.headers["Location"], "/")

    def test_register_validation_and_cold_start(self):
        t = self.token("/register")
        bad = self.c.post("/register", data={"username": "a", "password": "123456", "confirm": "123456", "csrf_token": t})
        self.assertEqual(bad.status_code, 400)
        bad = self.c.post("/register", data={"username": "demo", "password": "123456", "confirm": "123456", "csrf_token": t})
        self.assertEqual(bad.status_code, 400)
        ok = self.c.post("/register", data={"username": "newbie", "password": "secret1", "confirm": "secret1",
                                            "genres": ["Comedy", "Romance", "NotAGenre"], "csrf_token": t}, follow_redirects=True)
        self.assertEqual(ok.status_code, 200)
        # brand-new user with zero ratings must still get recommendations
        for m in ("hybrid", "cf", "content", "popular"):
            self.assertEqual(self.c.get("/recommendations?method=" + m).status_code, 200)
        api = self.c.get("/api/recommendations?limit=10").get_json()
        self.assertEqual(len(api["results"]), 10)

    def test_rating_api(self):
        self.login()
        t = self.token("/")
        h = {"X-CSRF-Token": t}
        r = self.c.post("/api/rate", json={"movie_id": 40, "rating": 5}, headers=h).get_json()
        self.assertTrue(r["ok"])
        r2 = self.c.post("/api/rate", json={"movie_id": 40, "rating": 2}, headers=h).get_json()
        self.assertEqual(r2["rating"], 2)
        self.assertEqual(r2["votes"], r["votes"])  # update, not duplicate
        self.assertEqual(self.c.post("/api/rate", json={"movie_id": 40, "rating": 9}, headers=h).status_code, 400)
        self.assertEqual(self.c.post("/api/rate", json={"movie_id": 9999, "rating": 3}, headers=h).status_code, 404)
        self.assertEqual(self.c.post("/api/rate", json={"movie_id": "x", "rating": 3}, headers=h).status_code, 400)
        self.assertEqual(self.c.post("/api/rate", json={"movie_id": 40, "rating": 3}).status_code, 400)  # no CSRF
        gone = self.c.post("/api/rate", json={"movie_id": 40, "rating": 0}, headers=h).get_json()
        self.assertEqual(gone["votes"], r["votes"] - 1)

    def test_rating_requires_login(self):
        t = self.token()
        r = self.c.post("/api/rate", json={"movie_id": 1, "rating": 4}, headers={"X-CSRF-Token": t})
        self.assertEqual(r.status_code, 401)

    def test_recommendations_change_after_rating(self):
        self.login("user05", "password123")
        t = self.token("/")
        before = [x["id"] for x in self.c.get("/api/recommendations?limit=10").get_json()["results"]]
        for mid in before[:3]:
            self.c.post("/api/rate", json={"movie_id": mid, "rating": 5}, headers={"X-CSRF-Token": t})
        after = [x["id"] for x in self.c.get("/api/recommendations?limit=10").get_json()["results"]]
        self.assertFalse(set(before[:3]) & set(after), "rated movies must not be recommended again")

    def test_engine_edge_cases(self):
        movies = [{"id": i, "title": "M%d" % i, "year": 2000, "genres": ["Drama"], "director": "D",
                   "actors": "A, B", "description": "a quiet story"} for i in range(1, 6)]
        for ratings in ([], [(1, 1, 5)], [(1, 1, 5), (1, 2, 5), (2, 1, 5), (2, 2, 5)]):  # empty / tiny / constant
            rec = Recommender(movies, ratings)
            for m in Recommender.METHODS:
                out = rec.recommend(1, 3, m)
                self.assertLessEqual(len(out), 3)
                for o in out:
                    self.assertTrue(1 <= o["score"] <= 5)
            self.assertEqual(len(rec.similar_items(1, 3)), 3)
            self.assertEqual(rec.recommend(999, 3, "hybrid")[0]["movie"]["id"] in range(1, 6), True)

    def test_evaluation_sanity(self):
        with appmod.app.app_context():
            appmod.model()  # train once
        ev = appmod.mm.evaluation(10)
        rating = {r["method"]: r for r in ev["rating"]}
        ranking = {r["method"]: r for r in ev["ranking"]}
        self.assertLess(rating["hybrid"]["rmse"], 1.5)
        self.assertGreater(ranking["hybrid"]["ndcg"], ranking["random"]["ndcg"])
        self.assertGreater(ranking["hybrid"]["precision"], ranking["random"]["precision"])


if __name__ == "__main__":
    unittest.main(verbosity=2)