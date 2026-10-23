(function () {
    var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

    function toast(msg) {
        var t = document.createElement("div");
        t.className = "toast";
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(function () { t.remove(); }, 2600);
    }

    function paint(box, rating) {
        box.dataset.rating = rating;
        box.querySelectorAll(".star").forEach(function (s) {
            s.classList.toggle("on", Number(s.dataset.v) <= rating);
            s.classList.remove("hover");
        });
    }

    function sendRating(box, rating) {
        if (box.dataset.auth !== "1") {
            window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname + window.location.search);
            return;
        }
        fetch("/api/rate", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
            body: JSON.stringify({ movie_id: Number(box.dataset.movie), rating: rating })
        })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!d.ok) { toast(d.error || "Could not save rating"); return; }
                paint(box, d.rating);
                toast(d.rating ? "Saved: " + d.rating + " star" + (d.rating > 1 ? "s" : "") : "Rating removed");
                var avg = document.getElementById("avgText"), votes = document.getElementById("votesText");
                if (avg) avg.textContent = d.votes ? d.avg.toFixed(2) : "No ratings yet";
                if (votes) votes.textContent = d.votes;
                var clear = document.querySelector(".clear-rating");
                if (clear && box.closest(".rate-box")) clear.hidden = !d.rating;
            })
            .catch(function () { toast("Network error. Please try again."); });
    }

    document.querySelectorAll(".stars").forEach(function (box) {
        var stars = box.querySelectorAll(".star");
        stars.forEach(function (s) {
            s.addEventListener("mouseenter", function () {
                stars.forEach(function (o) { o.classList.toggle("hover", Number(o.dataset.v) <= Number(s.dataset.v)); });
            });
            s.addEventListener("click", function () { sendRating(box, Number(s.dataset.v)); });
        });
        box.addEventListener("mouseleave", function () { stars.forEach(function (o) { o.classList.remove("hover"); }); });
    });

    document.querySelectorAll(".clear-rating").forEach(function (b) {
        b.addEventListener("click", function () {
            var box = document.querySelector('.rate-box .stars');
            if (box) sendRating(box, 0);
        });
    });

    document.querySelectorAll(".flash-x").forEach(function (b) {
        b.addEventListener("click", function () { b.parentElement.remove(); });
    });

    var toggle = document.getElementById("navToggle"), links = document.getElementById("navLinks");
    if (toggle) toggle.addEventListener("click", function () { links.classList.toggle("open"); });
})();