# CineMatch - Hybrid Movie Recommendation System

B.Tech final-year project. Flask + SQLite + a recommendation engine written in pure Python
(no numpy, no scikit-learn, no paid services).

## Features
- Hybrid recommender = item-based collaborative filtering + TF-IDF content-based + popularity
- Cold-start handling (favourite genres + Bayesian popularity), explanations ("Because you liked ...")
- Register / login (hashed passwords, CSRF protection), 5-star rating with live averages
- Search, genre filter, sorting, pagination, similar-movie suggestions, rating prediction
- Evaluation dashboard: RMSE, MAE, Precision@K, Recall@K, NDCG@K (5 repeated hold-out splits)
- JSON API: `/api/recommendations`, `/api/movies/<id>/similar`, `/api/rate`

## Run locally (Windows)
    cd movie-recommender
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    python app.py

Open http://127.0.0.1:5000  - demo login: `demo` / `demo123`
(other seeded users: `user01` ... `user60`, password `password123`).

## Tests
    python test_app.py

## Reset the database
    python seed_data.py --reset