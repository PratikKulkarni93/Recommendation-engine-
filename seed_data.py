"""Seeds the database with 70 movies and 60 synthetic users with realistic taste patterns.
Run directly to rebuild:  python seed_data.py --reset
"""
import os
import random
import sqlite3
import sys
import time

from werkzeug.security import generate_password_hash

import database

# (title, year, genres, director, actors, description)
MOVIES = [
    ("The Shawshank Redemption", 1994, "Drama", "Frank Darabont", "Tim Robbins, Morgan Freeman", "A banker wrongly convicted of murder forms a lasting friendship in prison and quietly plans his escape."),
    ("The Godfather", 1972, "Crime|Drama", "Francis Ford Coppola", "Marlon Brando, Al Pacino", "The aging head of a mafia family hands his empire to his reluctant youngest son."),
    ("The Dark Knight", 2008, "Action|Crime|Drama", "Christopher Nolan", "Christian Bale, Heath Ledger", "A masked vigilante faces an anarchic criminal mastermind who pushes Gotham city toward chaos."),
    ("Pulp Fiction", 1994, "Crime|Drama", "Quentin Tarantino", "John Travolta, Samuel L. Jackson, Uma Thurman", "Interwoven stories of hitmen, a boxer and a gangster wife unfold in sharp and darkly funny Los Angeles crime tales."),
    ("Forrest Gump", 1994, "Drama|Romance", "Robert Zemeckis", "Tom Hanks, Robin Wright", "A kind man with a low IQ drifts through decades of American history while pining for his childhood love."),
    ("Inception", 2010, "Action|Sci-Fi|Thriller", "Christopher Nolan", "Leonardo DiCaprio, Joseph Gordon-Levitt", "A thief who steals secrets from dreams is hired to plant an idea inside a target's subconscious."),
    ("The Matrix", 1999, "Action|Sci-Fi", "Lana Wachowski, Lilly Wachowski", "Keanu Reeves, Laurence Fishburne", "A hacker discovers reality is a simulation run by machines and joins a rebellion to free humanity."),
    ("Interstellar", 2014, "Adventure|Drama|Sci-Fi", "Christopher Nolan", "Matthew McConaughey, Anne Hathaway", "Astronauts travel through a wormhole searching for a new home for humanity as Earth fails."),
    ("Fight Club", 1999, "Drama|Thriller", "David Fincher", "Brad Pitt, Edward Norton", "An insomniac office worker and a soap salesman start an underground fighting club that spirals out of control."),
    ("Goodfellas", 1990, "Crime|Drama", "Martin Scorsese", "Robert De Niro, Ray Liotta, Joe Pesci", "The rise and fall of a young associate inside a New York mafia crew over three decades."),
    ("The Lord of the Rings: The Fellowship of the Ring", 2001, "Adventure|Fantasy", "Peter Jackson", "Elijah Wood, Ian McKellen", "A young hobbit and eight companions set out to destroy a powerful ring and save Middle-earth."),
    ("Star Wars: The Empire Strikes Back", 1980, "Action|Adventure|Sci-Fi", "Irvin Kershner", "Mark Hamill, Harrison Ford", "Rebel heroes scatter across the galaxy while the dark empire hunts them and a young pilot trains to be a Jedi."),
    ("Gladiator", 2000, "Action|Adventure|Drama", "Ridley Scott", "Russell Crowe, Joaquin Phoenix", "A betrayed Roman general becomes a gladiator and seeks revenge against the corrupt emperor."),
    ("Titanic", 1997, "Drama|Romance", "James Cameron", "Leonardo DiCaprio, Kate Winslet", "A young artist and an aristocrat fall in love aboard the doomed luxury ocean liner."),
    ("Jurassic Park", 1993, "Adventure|Sci-Fi|Thriller", "Steven Spielberg", "Sam Neill, Laura Dern, Jeff Goldblum", "Cloned dinosaurs escape their enclosures and terrorize visitors at a remote island theme park."),
    ("The Lion King", 1994, "Animation|Adventure|Family", "Roger Allers, Rob Minkoff", "Matthew Broderick, Jeremy Irons", "A young lion prince flees his kingdom after his father's death and must return to reclaim the throne."),
    ("Toy Story", 1995, "Animation|Comedy|Family", "John Lasseter", "Tom Hanks, Tim Allen", "A cowboy doll feels threatened when a flashy space ranger toy becomes his owner's new favourite."),
    ("Finding Nemo", 2003, "Animation|Adventure|Family", "Andrew Stanton", "Albert Brooks, Ellen DeGeneres", "An anxious clownfish crosses the ocean with a forgetful friend to rescue his captured son."),
    ("Spirited Away", 2001, "Animation|Fantasy|Family", "Hayao Miyazaki", "Rumi Hiiragi, Miyu Irino", "A girl wanders into a world of spirits and must work in a bathhouse to free her parents."),
    ("Parasite", 2019, "Drama|Thriller|Comedy", "Bong Joon-ho", "Song Kang-ho, Choi Woo-shik", "A poor family cleverly infiltrates the household of a wealthy family with unexpected consequences."),
    ("Whiplash", 2014, "Drama|Music", "Damien Chazelle", "Miles Teller, J.K. Simmons", "An ambitious young drummer is pushed to the edge by a ruthless conservatory instructor."),
    ("La La Land", 2016, "Comedy|Drama|Music|Romance", "Damien Chazelle", "Ryan Gosling, Emma Stone", "A jazz pianist and an aspiring actress chase their dreams and fall in love in Los Angeles."),
    ("The Silence of the Lambs", 1991, "Crime|Thriller|Horror", "Jonathan Demme", "Jodie Foster, Anthony Hopkins", "A young FBI trainee consults an imprisoned cannibalistic psychiatrist to catch another serial killer."),
    ("Se7en", 1995, "Crime|Thriller|Mystery", "David Fincher", "Brad Pitt, Morgan Freeman", "Two detectives hunt a killer who stages murders inspired by the seven deadly sins."),
    ("The Sixth Sense", 1999, "Mystery|Thriller|Drama", "M. Night Shyamalan", "Bruce Willis, Haley Joel Osment", "A child psychologist helps a frightened boy who claims he can see and speak with the dead."),
    ("Get Out", 2017, "Horror|Mystery|Thriller", "Jordan Peele", "Daniel Kaluuya, Allison Williams", "A young man visiting his girlfriend's family estate uncovers a disturbing secret hidden behind their warm welcome."),
    ("The Shining", 1980, "Horror|Thriller", "Stanley Kubrick", "Jack Nicholson, Shelley Duvall", "A writer caretaking an isolated mountain hotel in winter slowly descends into violent madness."),
    ("Alien", 1979, "Horror|Sci-Fi", "Ridley Scott", "Sigourney Weaver, Tom Skerritt", "The crew of a cargo spaceship is stalked by a deadly creature that has slipped aboard."),
    ("Blade Runner 2049", 2017, "Sci-Fi|Drama|Thriller", "Denis Villeneuve", "Ryan Gosling, Harrison Ford", "A young replicant officer uncovers a long-buried secret that could plunge society into chaos."),
    ("Mad Max: Fury Road", 2015, "Action|Adventure|Sci-Fi", "George Miller", "Tom Hardy, Charlize Theron", "In a desert wasteland a drifter and a rebel warrior race a war rig to escape a tyrant."),
    ("Avengers: Endgame", 2019, "Action|Adventure|Sci-Fi", "Anthony Russo, Joe Russo", "Robert Downey Jr., Chris Evans", "The remaining superheroes assemble for a final attempt to undo the destruction of half the universe."),
    ("Iron Man", 2008, "Action|Adventure|Sci-Fi", "Jon Favreau", "Robert Downey Jr., Gwyneth Paltrow", "A billionaire weapons engineer builds a powered armor suit after escaping captivity."),
    ("Black Panther", 2018, "Action|Adventure|Sci-Fi", "Ryan Coogler", "Chadwick Boseman, Michael B. Jordan", "The new king of a hidden technologically advanced African nation faces a challenger to the throne."),
    ("Spider-Man: Into the Spider-Verse", 2018, "Animation|Action|Adventure", "Bob Persichetti, Peter Ramsey, Rodney Rothman", "Shameik Moore, Hailee Steinfeld", "A teenager from Brooklyn meets spider heroes from parallel dimensions and learns to wear the mask."),
    ("The Avengers", 2012, "Action|Adventure|Sci-Fi", "Joss Whedon", "Robert Downey Jr., Chris Evans", "Earth's mightiest heroes must unite to stop an alien invasion led by a vengeful trickster god."),
    ("Die Hard", 1988, "Action|Thriller", "John McTiernan", "Bruce Willis, Alan Rickman", "A New York policeman battles terrorists who have taken over a skyscraper during a Christmas party."),
    ("Terminator 2: Judgment Day", 1991, "Action|Sci-Fi", "James Cameron", "Arnold Schwarzenegger, Linda Hamilton", "A reprogrammed cyborg protects a boy from a more advanced shape-shifting assassin sent from the future."),
    ("Back to the Future", 1985, "Adventure|Comedy|Sci-Fi", "Robert Zemeckis", "Michael J. Fox, Christopher Lloyd", "A teenager accidentally travels thirty years into the past in a time machine built from a sports car."),
    ("Groundhog Day", 1993, "Comedy|Fantasy|Romance", "Harold Ramis", "Bill Murray, Andie MacDowell", "A cynical weatherman finds himself reliving the same small-town winter day again and again."),
    ("The Grand Budapest Hotel", 2014, "Comedy|Adventure|Drama", "Wes Anderson", "Ralph Fiennes, Tony Revolori", "A legendary concierge and his young lobby boy get tangled in the theft of a priceless painting."),
    ("Superbad", 2007, "Comedy", "Greg Mottola", "Jonah Hill, Michael Cera", "Two awkward high school friends try to buy alcohol for a party before graduation."),
    ("The Hangover", 2009, "Comedy", "Todd Phillips", "Bradley Cooper, Zach Galifianakis", "Three friends wake up after a bachelor party in Las Vegas with no memory and a missing groom."),
    ("3 Idiots", 2009, "Comedy|Drama", "Rajkumar Hirani", "Aamir Khan, R. Madhavan, Sharman Joshi", "Two friends search for their long-lost companion and recall their engineering college days of rebellion and learning."),
    ("Dangal", 2016, "Drama|Sport", "Nitesh Tiwari", "Aamir Khan, Fatima Sana Shaikh", "A former wrestler trains his daughters to become champion wrestlers against social expectations."),
    ("Lagaan", 2001, "Drama|Sport|Musical", "Ashutosh Gowariker", "Aamir Khan, Gracy Singh", "Villagers accept a cricket challenge from colonial officers to win relief from crushing taxes."),
    ("Dilwale Dulhania Le Jayenge", 1995, "Romance|Drama|Comedy", "Aditya Chopra", "Shah Rukh Khan, Kajol", "Two young travellers fall in love in Europe but must win over a strict father in Punjab."),
    ("Zindagi Na Milegi Dobara", 2011, "Comedy|Drama|Adventure", "Zoya Akhtar", "Hrithik Roshan, Farhan Akhtar, Abhay Deol", "Three friends take a bachelor road trip across Spain that changes how they see life and fear."),
    ("Gully Boy", 2019, "Drama|Music", "Zoya Akhtar", "Ranveer Singh, Alia Bhatt", "A young man from the slums of Mumbai finds his voice and rises as a street rapper."),
    ("Baahubali: The Beginning", 2015, "Action|Adventure|Drama", "S. S. Rajamouli", "Prabhas, Rana Daggubati", "A young man raised in a village discovers his royal heritage and a kingdom torn by betrayal."),
    ("RRR", 2022, "Action|Drama|Adventure", "S. S. Rajamouli", "N. T. Rama Rao Jr., Ram Charan", "Two revolutionaries form a powerful friendship while fighting colonial rule in 1920s India."),
    ("Andhadhun", 2018, "Thriller|Comedy|Crime", "Sriram Raghavan", "Ayushmann Khurrana, Tabu", "A pianist pretending to be blind witnesses a murder and is dragged into a web of lies."),
    ("Drishyam", 2015, "Thriller|Crime|Drama", "Nishikant Kamat", "Ajay Devgn, Tabu", "A cable operator uses cinematic cunning to protect his family after an accidental death."),
    ("Schindler's List", 1993, "Drama|History", "Steven Spielberg", "Liam Neeson, Ralph Fiennes", "A businessman saves more than a thousand Jewish workers from the Holocaust by employing them in his factory."),
    ("Saving Private Ryan", 1998, "Drama|War|Action", "Steven Spielberg", "Tom Hanks, Matt Damon", "A squad of soldiers crosses enemy lines after the Normandy landings to bring one paratrooper home."),
    ("Braveheart", 1995, "Drama|History|War|Action", "Mel Gibson", "Mel Gibson, Sophie Marceau", "A Scottish warrior leads a rebellion against the tyrannical English king in the thirteenth century."),
    ("The Notebook", 2004, "Romance|Drama", "Nick Cassavetes", "Ryan Gosling, Rachel McAdams", "A poor young man and a wealthy girl fall in love one summer and are separated by class."),
    ("Pride & Prejudice", 2005, "Romance|Drama", "Joe Wright", "Keira Knightley, Matthew Macfadyen", "A spirited young woman and a proud wealthy gentleman overcome misjudgement in Regency England."),
    ("Eternal Sunshine of the Spotless Mind", 2004, "Drama|Romance|Sci-Fi", "Michel Gondry", "Jim Carrey, Kate Winslet", "A heartbroken man undergoes a procedure to erase memories of his ex and rediscovers what he loved."),
    ("Coco", 2017, "Animation|Family|Fantasy|Music", "Lee Unkrich", "Anthony Gonzalez, Gael Garcia Bernal", "A boy who dreams of becoming a musician enters the land of the dead to uncover his family history."),
    ("Inside Out", 2015, "Animation|Comedy|Family", "Pete Docter", "Amy Poehler, Phyllis Smith", "The emotions inside a young girl's mind struggle to guide her through a difficult move to a new city."),
    ("Up", 2009, "Animation|Adventure|Comedy", "Pete Docter", "Ed Asner, Jordan Nagai", "An elderly widower ties thousands of balloons to his house and flies to South America with a young stowaway."),
    ("Shutter Island", 2010, "Mystery|Thriller|Drama", "Martin Scorsese", "Leonardo DiCaprio, Mark Ruffalo", "A US marshal investigates a patient's disappearance from a remote island hospital for the criminally insane."),
    ("Oppenheimer", 2023, "Drama|History|Thriller", "Christopher Nolan", "Cillian Murphy, Emily Blunt", "The physicist who led the development of the atomic bomb wrestles with the consequences of his creation."),
    ("Dune", 2021, "Sci-Fi|Adventure|Drama", "Denis Villeneuve", "Timothee Chalamet, Zendaya", "A noble family takes control of a desert planet whose spice is the most valuable substance in the universe."),
    ("Knives Out", 2019, "Comedy|Crime|Mystery", "Rian Johnson", "Daniel Craig, Ana de Armas", "A detective investigates the death of a wealthy novelist surrounded by his quarrelling family."),
    ("The Prestige", 2006, "Drama|Mystery|Sci-Fi", "Christopher Nolan", "Christian Bale, Hugh Jackman", "Two rival stage magicians in Victorian London wage a dangerous war of secrets and obsession."),
    ("Joker", 2019, "Crime|Drama|Thriller", "Todd Phillips", "Joaquin Phoenix, Robert De Niro", "A struggling clown in a decaying city descends into madness and becomes a symbol of violent unrest."),
    ("Top Gun: Maverick", 2022, "Action|Drama", "Joseph Kosinski", "Tom Cruise, Miles Teller", "A veteran naval aviator trains a new generation of elite pilots for a nearly impossible mission."),
    ("Mission: Impossible - Fallout", 2018, "Action|Adventure|Thriller", "Christopher McQuarrie", "Tom Cruise, Henry Cavill", "A secret agent races against time after a mission goes wrong and plutonium falls into dangerous hands."),
    ("The Social Network", 2010, "Drama|Biography", "David Fincher", "Jesse Eisenberg, Andrew Garfield", "A Harvard student creates a social website that becomes a global phenomenon and costs him his friendships."),
]


def seed(path, n_users=60, seed_value=42):
    database.init_db(path)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    if con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]:
        con.close()
        return
    con.executemany(
        "INSERT INTO movies(title, year, genres, director, actors, description) VALUES (?,?,?,?,?,?)", MOVIES
    )
    rng = random.Random(seed_value)
    genres = sorted({g for m in MOVIES for g in m[2].split("|")})
    mg = {i + 1: set(m[2].split("|")) for i, m in enumerate(MOVIES)}
    quality = {i: rng.gauss(0, 0.5) for i in mg}
    fast = lambda pw: generate_password_hash(pw, method="pbkdf2:sha256")

    users = [("demo", fast("demo123"), ["Sci-Fi", "Thriller", "Drama"], 14)]
    shared_pw = fast("password123")
    for n in range(1, n_users + 1):
        users.append(("user%02d" % n, shared_pw, rng.sample(genres, 3), rng.randint(15, 34)))

    now = time.time()
    for idx, (name, pw, likes, count) in enumerate(users, start=1):
        con.execute(
            "INSERT INTO users(username, password_hash, fav_genres) VALUES (?,?,?)", (name, pw, ",".join(likes[:2]))
        )
        bias = rng.gauss(0, 0.3)
        # weighted sampling without replacement: movies in liked genres are more likely to be watched
        keyed = []
        for mid, gs in mg.items():
            w = 1 + 5 * len(gs & set(likes)) / len(gs)
            keyed.append((rng.random() ** (1.0 / w), mid))
        keyed.sort(reverse=True)
        for _, mid in keyed[:count]:
            aff = len(mg[mid] & set(likes)) / len(mg[mid])
            raw = 2.9 + 1.6 * aff + quality[mid] + bias + rng.gauss(0, 0.6)
            rating = max(1, min(5, int(round(raw))))
            con.execute(
                "INSERT INTO ratings(user_id, movie_id, rating, updated_at) VALUES (?,?,?,?)",
                (idx, mid, rating, now - rng.randint(0, 86400 * 90)),
            )
    con.commit()
    con.close()


if __name__ == "__main__":
    target = os.environ.get("RECSYS_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "recommender.db"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if "--reset" in sys.argv and os.path.exists(target):
        os.remove(target)
    seed(target)
    print("Database ready:", target)