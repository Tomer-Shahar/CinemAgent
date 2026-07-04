import requests
from bs4 import BeautifulSoup

def scrape_cinema_page(url: str) -> str:
    """Scrapes raw text layout from a given Tel Aviv cinema URL, preserving link hrefs."""
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract only the movie slider boxes for the Cinemateque homepage to prevent context overflow
    if "cinema.co.il" in url and (url.rstrip('/').endswith("cinema.co.il") or "main" in url):
        sliders = soup.find_all(class_="movie-slider-box")
        if sliders:
            html_content = "".join([str(s) for s in sliders])
            soup = BeautifulSoup(html_content, 'html.parser')
    # Strip scripts/styles to save token window
    for script in soup(["script", "style"]):
        script.extract()
        
    # Replace link tags with [text](href) to preserve ticket links for the agent
    from urllib.parse import urljoin
    for a in soup.find_all('a', href=True):
        link_text = a.get_text().strip()
        link_url = a['href']
        # Resolve relative URLs
        if link_url.startswith('/') or not link_url.startswith('http'):
            link_url = urljoin(url, link_url)
        a.replace_with(f" [{link_text}]({link_url}) ")
        
    # Replace image tags with ![alt](src) to preserve movie posters for fallback
    for img in soup.find_all('img', src=True):
        alt_text = img.get('alt', '').strip() or 'Poster'
        img_url = img['src']
        if img_url.startswith('/') or not img_url.startswith('http'):
            img_url = urljoin(url, img_url)
        img.replace_with(f" ![{alt_text}]({img_url}) ")
        
    # Strip empty lines and extra whitespace to minimize token usage
    lines = [line.strip() for line in soup.get_text().splitlines() if line.strip()]
    cleaned_text = "\n".join(lines)
    
    # Detail pages (like events or calendar bookings) are very short; limit their length to 6,000 chars.
    # Main schedule index pages are limited to 20,000 chars.
    if "/event/" in url or "/calendar/" in url:
        return cleaned_text[:6000]
    return cleaned_text[:20000]

def search_imdb_autocomplete(query: str) -> str:
    """Queries the IMDb public autocomplete suggestion endpoint and returns the best matching imdbID."""
    import requests
    import urllib.parse
    
    try:
        # Clean query: alphanumeric and spaces only
        query_clean = "".join(c for c in query if c.isalnum() or c.isspace()).strip()
        if not query_clean:
            return None
        query_encoded = urllib.parse.quote(query_clean.lower())
        first_char = query_encoded[0]
        url = f"https://v3.sg.media-imdb.com/suggestion/{first_char}/{query_encoded}.json"
        
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            results = data.get("d", [])
            if results:
                # Prioritize movies (qid == 'movie' or 'feature')
                for item in results:
                    qid = item.get("qid", "")
                    if qid in ("movie", "feature"):
                        return item.get("id")
                # Fallback to the first result of any type
                return results[0].get("id")
    except Exception as e:
        print(f"IMDb Autocomplete error for '{query}': {e}")
    return None

def search_imdb_data(movie_titles) -> dict:
    """Fetches movie metadata (IMDb url/score, RT score, Poster, Plot, Year) from OMDb API for movie titles."""
    import requests
    import os
    import re
    
    if isinstance(movie_titles, str):
        movie_titles = [movie_titles]
        
    api_key = os.environ.get("OMDB_KEY")
    results = {}
    
    if not api_key:
        for title in movie_titles:
            results[title] = {
                "imdb_url": f"https://www.imdb.com/find?q={title}",
                "imdb_score": "N/A",
                "rt_score": "N/A",
                "poster_url": "",
                "plot": "",
                "year": ""
            }
        return results
        
    for title in movie_titles:
        try:
            data = None
            
            # --- TIER 1: Try OMDb Exact Match ---
            url = f"http://www.omdbapi.com/?apikey={api_key}&t={title}"
            try:
                response = requests.get(url, timeout=5)
                res_data = response.json()
                if res_data.get("Response") == "True":
                    data = res_data
            except Exception:
                pass
                
            # --- TIER 1.5: Swap 'and' for '&' ---
            if (not data or data.get("Response") != "True") and " and " in title:
                alt_title = title.replace(" and ", " & ")
                url = f"http://www.omdbapi.com/?apikey={api_key}&t={alt_title}"
                try:
                    response = requests.get(url, timeout=5)
                    res_data = response.json()
                    if res_data.get("Response") == "True":
                        data = res_data
                except Exception:
                    pass

            # --- TIER 2: Try IMDb Autocomplete fallback ---
            if not data or data.get("Response") != "True":
                imdb_id = search_imdb_autocomplete(title)
                if imdb_id:
                    id_url = f"http://www.omdbapi.com/?apikey={api_key}&i={imdb_id}"
                    try:
                        response = requests.get(id_url, timeout=5)
                        res_data = response.json()
                        if res_data.get("Response") == "True":
                            data = res_data
                    except Exception:
                        pass

            # --- TIER 3: Try OMDb Search + Local difflib fuzzy selection ---
            if not data or data.get("Response") != "True":
                import difflib
                search_url = f"http://www.omdbapi.com/?apikey={api_key}&s={title}"
                try:
                    search_res = requests.get(search_url, timeout=5).json()
                    if search_res.get("Response") == "True" and search_res.get("Search"):
                        search_items = search_res.get("Search", [])
                        titles_list = [item.get("Title") for item in search_items if "Title" in item]
                        
                        # Fuzzy compare titles to our messy input
                        matches = difflib.get_close_matches(title, titles_list, n=1, cutoff=0.3)
                        if matches:
                            best_match = matches[0]
                            for item in search_items:
                                if item.get("Title") == best_match:
                                    matched_id = item.get("imdbID")
                                    id_url = f"http://www.omdbapi.com/?apikey={api_key}&i={matched_id}"
                                    res_data = requests.get(id_url, timeout=5).json()
                                    if res_data.get("Response") == "True":
                                        data = res_data
                                    break
                except Exception:
                    pass
                    
            # --- TIER 4: Try first two words search if still failed ---
            if not data or data.get("Response") != "True":
                words = title.split()
                if len(words) > 2:
                    import difflib
                    short_title = " ".join(words[:2])
                    search_url = f"http://www.omdbapi.com/?apikey={api_key}&s={short_title}"
                    try:
                        search_resp = requests.get(search_url, timeout=5).json()
                        if search_resp.get("Response") == "True" and search_resp.get("Search"):
                            search_items = search_resp.get("Search", [])
                            selected_id = search_items[0]["imdbID"]
                            for item in search_items:
                                if any(w.lower() in item["Title"].lower() for w in words):
                                    selected_id = item["imdbID"]
                                    break
                            id_url = f"http://www.omdbapi.com/?apikey={api_key}&i={selected_id}"
                            res_data = requests.get(id_url, timeout=5).json()
                            if res_data.get("Response") == "True":
                                data = res_data
                    except Exception:
                        pass
            
            if data and data.get("Response") == "True":
                imdb_score = data.get("imdbRating", "N/A")
                imdb_id = data.get("imdbID")
                imdb_url = f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else f"https://www.imdb.com/find?q={title}"
                
                rt_score = "N/A"
                for rating in data.get("Ratings", []):
                    if rating.get("Source") == "Rotten Tomatoes":
                        rt_score = rating.get("Value")
                        break
                        
                raw_plot = data.get("Plot")
                plot_val = raw_plot if raw_plot and raw_plot != "N/A" else ""
                
                year_val = data.get("Year", "")
                if year_val:
                    match = re.search(r'\d{4}', year_val)
                    year_val = match.group(0) if match else year_val
                        
                results[title] = {
                    "imdb_url": imdb_url,
                    "imdb_score": imdb_score,
                    "rt_score": rt_score,
                    "poster_url": data.get("Poster") if data.get("Poster") != "N/A" else "",
                    "plot": plot_val,
                    "year": year_val
                }
            else:
                results[title] = {
                    "imdb_url": f"https://www.imdb.com/find?q={title}",
                    "imdb_score": "N/A",
                    "rt_score": "N/A",
                    "poster_url": "",
                    "plot": "",
                    "year": ""
                }
        except Exception as e:
            results[title] = {
                "imdb_url": f"https://www.imdb.com/find?q={title}",
                "imdb_score": "N/A",
                "rt_score": "N/A",
                "poster_url": "",
                "plot": "",
                "year": ""
            }
            
    return results

def save_screenings_to_db(screenings: list) -> str:
    """Saves a list of movie screenings to the Supabase database, overwriting existing records.
    Each screening dict can contain: 'title', 'date', 'time', 'cinema', 'year', and 'ticket_url'.
    """
    from supabase import create_client, Client
    import os
    
    url = os.environ.get("SUPABASE_PROJECT_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return "Error: Supabase environment variables not found in .env"
        
    try:
        # Also save the screenings locally as a JSON file
        import json
        output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "screenings.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(screenings, f, indent=2, ensure_ascii=False)

        supabase: Client = create_client(url, key)
        
        # Overwrite logic: delete existing screenings for the current cinema(s) in this batch
        cinemas = list(set(s.get("cinema") for s in screenings if s.get("cinema")))
        if cinemas:
            supabase.table("screenings").delete().in_("cinema", cinemas).execute()
            
        # Perform bulk insert into 'screenings' table
        response = supabase.table("screenings").insert(screenings).execute()
        return f"Successfully saved {len(screenings)} screenings to the Supabase database and locally to src/output/screenings.json."
    except Exception as e:
        return f"Error saving to database: {str(e)}"

# Map strings to actual callable functions for our loop execution stage
TOOL_MANIFEST = {
    "scrape_cinema_page": scrape_cinema_page,
    "search_imdb_data": search_imdb_data,
    "save_screenings_to_db": save_screenings_to_db
}