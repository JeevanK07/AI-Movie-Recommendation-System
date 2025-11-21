import streamlit as st
import pandas as pd
import requests
import pickle
import time
import re

# -------------------------------------------------
# STREAMLIT CONFIG
# -------------------------------------------------
st.set_page_config(page_title="AI Movie Recommender", layout="wide")

TMDB_API_KEY = "858b753c5a8668245484bd49f654309f"


# -------------------------------------------------
# SAFE REQUEST FUNCTION
# -------------------------------------------------
def safe_request(url, retries=3, delay=1, timeout=5):
    for _ in range(retries):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        time.sleep(delay)
    return None


# -------------------------------------------------
# YOUTUBE EMBED FIX
# -------------------------------------------------
def convert_to_embed(url):
    if not url:
        return None
    if "watch?v=" in url:
        key = url.split("watch?v=")[-1]
        return f"https://www.youtube.com/embed/{key}"
    return None


# -------------------------------------------------
# PAGE BANNER + CSS
# -------------------------------------------------
def show_html_banner():
    st.markdown(
        """
        <style>
            body {margin:0; padding:0;}
            .hero {
                padding: 40px;
                width: 100%;
                text-align: center;
                background: linear-gradient(to right, #0a0a0a, #1a1a1a);
                color: white;
                border-radius: 12px;
                margin-bottom: 15px;
            }
            .movie-box {
                background: #000;
                padding: 20px;
                color: white;
                border-radius: 15px;
                box-shadow: 0 0 15px rgba(255,255,255,0.1);
            }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div class='hero'>
            <h1>🎬 AI Movie Recommendation System</h1>
            <p>Discover movies by name or genre, watch trailers, and save to watchlist.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -------------------------------------------------
# LOAD MOVIE DATA
# -------------------------------------------------
with open("movie_data.pkl", "rb") as f:
    movies, cosine_sim = pickle.load(f)

required = {"movie_id", "title", "overview", "tags"}
if not required.issubset(set(movies.columns)):
    st.error("❌ movie_data.pkl missing required columns.")
    st.stop()


# -------------------------------------------------
# UNIVERSAL TAG EXTRACTOR
# -------------------------------------------------
def extract_tags(value):
    """
    Supports:
    - "action|thriller|space"
    - ["action","space"]
    - "action thriller space"
    """
    if isinstance(value, list):
        return [v.strip().lower() for v in value]

    if isinstance(value, str):
        parts = re.split(r"[|, ]+", value)
        return [p.strip().lower() for p in parts if len(p.strip()) > 2]

    return []


# Build list of all single-word tags
all_tags_set = set()
for t in movies["tags"]:
    tags = extract_tags(t)
    for tag in tags:
        all_tags_set.add(tag.capitalize())

all_tags = sorted(list(all_tags_set))


# -------------------------------------------------
# TMDB HELPERS
# -------------------------------------------------
@st.cache_data
def fetch_poster(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}"
    data = safe_request(url)
    if not data:
        return None
    p = data.get("poster_path")
    return f"https://image.tmdb.org/t/p/w500{p}" if p else None


@st.cache_data
def fetch_movie_details(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}"
    data = safe_request(url)
    if not data:
        return None
    return {
        "title": data.get("title", ""),
        "overview": data.get("overview", ""),
        "rating": data.get("vote_average", "N/A"),
        "release": data.get("release_date", "N/A"),
        "genres": ", ".join([g["name"] for g in data.get("genres", [])])
    }


@st.cache_data
def fetch_trailer(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
    data = safe_request(url)
    if not data:
        return None

    # Prefer official YouTube trailer
    for v in data.get("results", []):
        if v.get("type") == "Trailer" and v.get("site") == "YouTube":
            return f"https://www.youtube.com/watch?v={v.get('key')}"

    return None


# -------------------------------------------------
# RECOMMENDATION FUNCTIONS
# -------------------------------------------------
def get_recommendations_by_title(title):
    if title not in movies["title"].values:
        return pd.DataFrame()

    idx = movies[movies["title"] == title].index[0]
    sim_scores = sorted(
        list(enumerate(cosine_sim[idx])),
        key=lambda x: x[1],
        reverse=True
    )

    indices = [i for i, _ in sim_scores[1:11]]
    return movies.iloc[indices]


def get_recommendations_by_tag(tag):
    tag = tag.lower()
    mask = movies["tags"].apply(
        lambda x: tag in extract_tags(x)
    )
    return movies[mask].head(10)


# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
show_html_banner()

for key in ["popup_movie_id", "recommendations", "watchlist"]:
    if key not in st.session_state:
        st.session_state[key] = [] if key == "watchlist" else None


# -------------------------------------------------
# MODE SELECTOR
# -------------------------------------------------
mode = st.radio("Select mode:", ["By Movie Name", "By Genre"], horizontal=True)

if mode == "By Movie Name":
    selected_movie = st.selectbox("Choose a movie:", movies["title"])
    if st.button("Recommend"):
        st.session_state.recommendations = get_recommendations_by_title(selected_movie)
        st.session_state.popup_movie_id = None

else:
    selected_tag = st.selectbox("Choose Genre:", all_tags)
    if st.button("Find Movies"):
        st.session_state.recommendations = get_recommendations_by_tag(selected_tag)
        st.session_state.popup_movie_id = None


# -------------------------------------------------
# DISPLAY RECOMMENDATIONS
# -------------------------------------------------
if st.session_state.recommendations is not None:
    recs = st.session_state.recommendations.reset_index(drop=True)
    st.write("### 🎯 Recommended Movies")

    for i in range(0, len(recs), 5):
        cols = st.columns(5)
        for col, j in zip(cols, range(i, i + 5)):
            if j < len(recs):
                row = recs.iloc[j]
                poster = fetch_poster(row["movie_id"])
                with col:
                    if poster:
                        st.image(poster, width=150)
                    st.write(f"**{row['title']}**")
                    if st.button("More About", key=f"more_{row['movie_id']}"):
                        st.session_state.popup_movie_id = row["movie_id"]


# -------------------------------------------------
# MOVIE DETAILS POPUP (WITH AUTO-SCROLL)
# -------------------------------------------------
if st.session_state.popup_movie_id:

    movie_id = st.session_state.popup_movie_id
    details = fetch_movie_details(movie_id)
    poster = fetch_poster(movie_id)
    trailer = fetch_trailer(movie_id)
    trailer_embed = convert_to_embed(trailer)

    # Auto Scroll
    st.markdown(f"<div id='detail'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <script>
            document.getElementById('detail').scrollIntoView({behavior:'smooth'});
        </script>
        """,
        unsafe_allow_html=True,
    )

    title_q = details["title"].replace(" ", "+")

    st.markdown("<div class='movie-box'>", unsafe_allow_html=True)

    st.markdown(f"## 🎬 {details['title']}")

    if poster:
        st.image(poster, width=250)

    st.write(f"**⭐ Rating:** {details['rating']}")
    st.write(f"**📅 Release:** {details['release']}")
    st.write(f"**🎭 Genres:** {details['genres']}")
    

    st.write("### 📖 Overview")
    st.write(details["overview"])
    st.markdown(
        f"""
        
          <h4> For More Information:</h4>
           <a href="https://www.themoviedb.org/movie/{movie_id}" target="_blank">TMDB Page</a>

        
        """,
        unsafe_allow_html=True,
    )

    

    st.write("### 🎞 Trailer")
    if trailer_embed:
        st.components.v1.iframe(trailer_embed, height=300)
    else:
        st.info("Trailer not available.")

    st.write("### 🔗 Direct Links")
    st.markdown(
        f"""
        <ul>
            <li><a href="https://www.imdb.com/find?q={title_q}" target="_blank">IMDB Search</a></li>
            <li><a href="https://www.themoviedb.org/movie/{movie_id}" target="_blank">TMDB Page</a></li>
            <li><a href="https://www.google.com/search?q=watch+{title_q}+online" target="_blank">Watch Online</a></li>
            <li><a href="https://www.youtube.com/results?search_query={title_q}+full+movie" target="_blank">YouTube Search</a></li>
            <li><a href="https://www.netflix.com/search?q={title_q}" target="_blank">Netflix Search</a></li>
            <li><a href="https://www.primevideo.com/search?phrase={title_q}" target="_blank">Amazon Prime</a></li>
        </ul>
        """,
        unsafe_allow_html=True,
    )

    # ADD TO WATCHLIST
    if st.button("➕ Add to Watchlist"):
        if movie_id not in [m["movie_id"] for m in st.session_state.watchlist]:
            st.session_state.watchlist.append({
                "movie_id": movie_id,
                "title": details["title"],
                "poster": poster
            })
            st.success("Added to Watchlist!")
        else:
            st.info("Already in watchlist.")

    st.markdown("</div>", unsafe_allow_html=True)


# -------------------------------------------------
# SIDEBAR WATCHLIST
# -------------------------------------------------
st.sidebar.header("🎯 Your Watchlist")

if not st.session_state.watchlist:
    st.sidebar.write("No movies added.")
else:
    new_list = []
    for item in st.session_state.watchlist:
        st.sidebar.markdown(f"**{item['title']}**")
        if item["poster"]:
            st.sidebar.image(item["poster"], width=120)

        if st.sidebar.button("Remove", key=f"rm_{item['movie_id']}"):
            continue
        new_list.append(item)

    st.session_state.watchlist = new_list
