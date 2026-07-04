import requests
from bs4 import BeautifulSoup

def scrape_cinema_page(url: str) -> str:
    """Scrapes raw text layout from a given Tel Aviv cinema URL, preserving link hrefs."""
    import urllib.parse
    
    # Intercept SharePoint list pages on tel-aviv.gov.il to retrieve data directly from public REST API
    if "tel-aviv.gov.il" in url and "ListID=" in url and "ItemID=" in url:
        try:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(url)
            params = parse_qs(parsed_url.query)
            web_id = params.get("WebID", [""])[0].strip("{}")
            list_id = params.get("ListID", [""])[0].strip("{}")
            item_id = params.get("ItemID", [""])[0].strip("{}")
            
            site_id = "24aa409e-01ed-482e-b0ed-1956972addb1"
            view_list = urllib.parse.quote('תצוגת דף פריט ראשי - לא לגעת')
            
            api_url = f"https://www.tel-aviv.gov.il/_vti_bin/TlvSP2013PublicSite/TlvItem.svc/GetItemByViewForEvent/{site_id}/{web_id}/{list_id}/{view_list}/{item_id}"
            
            r = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                fields = data.get("Fields", [])
                text_parts = []
                for f in fields:
                    caption = f.get("Caption", "")
                    val = f.get("Value", "")
                    if val:
                        val_cleaned = BeautifulSoup(str(val), 'html.parser').get_text().strip()
                        text_parts.append(f"{caption}: {val_cleaned}")
                return "\n".join(text_parts)
        except Exception as e:
            print(f"Error querying Tel Aviv REST API: {e}")

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract only the movie slider boxes for the Cinemateque homepage to prevent context overflow
    # Extract only the movie slider boxes for the Cinemateque homepage to prevent context overflow
    if "cinema.co.il" in url and (url.rstrip('/').endswith("cinema.co.il") or "main" in url):
        slides = soup.find_all(class_="movie-slid")
        if slides:
            import concurrent.futures
            
            def process_slide(slide):
                try:
                    a_tags = slide.find_all('a', href=True)
                    event_url = None
                    for tag in a_tags:
                        href = tag['href']
                        if "/event/" in href:
                            event_url = href
                            break
                            
                    if event_url:
                        if not event_url.startswith('http'):
                            event_url = urllib.parse.urljoin("https://www.cinema.co.il/", event_url)
                        
                        # Find Hebrew text elements specifically inside this slide
                        for el in slide.find_all(text=True):
                            heb_title = el.strip()
                            # Check if contains Hebrew characters (range 1424-1514)
                            if heb_title and len(heb_title) > 2 and any(1424 <= ord(c) <= 1514 for c in heb_title):
                                if "לפרטים" in heb_title or "לרכישה" in heb_title or "/" in heb_title:
                                    continue
                                r = requests.get(event_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
                                if r.status_code == 200:
                                    sub_soup = BeautifulSoup(r.text, 'html.parser')
                                    for text in sub_soup.stripped_strings:
                                        if heb_title in text and "|" in text:
                                            el.replace_with(text)
                                            return
                except Exception:
                    pass
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                list(executor.map(process_slide, slides))
                
            html_content = "".join([str(s) for s in slides])
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
    import urllib.parse
    
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
            
            # --- TIER 1: Try IMDb Autocomplete first (ranked by popularity/relevance) ---
            imdb_id = search_imdb_autocomplete(title)
            if imdb_id:
                id_url = f"http://www.omdbapi.com/?apikey={api_key}&i={imdb_id}&plot=full"
                try:
                    response = requests.get(id_url, timeout=5)
                    res_data = response.json()
                    if res_data.get("Response") == "True":
                        data = res_data
                except Exception:
                    pass
                    
            # --- TIER 2: Try OMDb Exact Match as fallback ---
            if not data or data.get("Response") != "True":
                url = f"http://www.omdbapi.com/?apikey={api_key}&t={urllib.parse.quote(title)}&plot=full"
                try:
                    response = requests.get(url, timeout=5)
                    res_data = response.json()
                    if res_data.get("Response") == "True":
                        data = res_data
                except Exception:
                    pass
                    
            # --- TIER 2.5: Swap 'and' for '&' ---
            if (not data or data.get("Response") != "True") and " and " in title:
                alt_title = title.replace(" and ", " & ")
                url = f"http://www.omdbapi.com/?apikey={api_key}&t={urllib.parse.quote(alt_title)}&plot=full"
                try:
                    response = requests.get(url, timeout=5)
                    res_data = response.json()
                    if res_data.get("Response") == "True":
                        data = res_data
                except Exception:
                    pass

            # --- TIER 3: Try OMDb Search + Local difflib fuzzy selection ---
            if not data or data.get("Response") != "True":
                import difflib
                search_url = f"http://www.omdbapi.com/?apikey={api_key}&s={urllib.parse.quote(title)}"
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
                                    id_url = f"http://www.omdbapi.com/?apikey={api_key}&i={matched_id}&plot=full"
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
                    search_url = f"http://www.omdbapi.com/?apikey={api_key}&s={urllib.parse.quote(short_title)}"
                    try:
                        search_resp = requests.get(search_url, timeout=5).json()
                        if search_resp.get("Response") == "True" and search_resp.get("Search"):
                            search_items = search_resp.get("Search", [])
                            selected_id = search_items[0]["imdbID"]
                            for item in search_items:
                                if any(w.lower() in item["Title"].lower() for w in words):
                                    selected_id = item["imdbID"]
                                    break
                            id_url = f"http://www.omdbapi.com/?apikey={api_key}&i={selected_id}&plot=full"
                            res_data = requests.get(id_url, timeout=5).json()
                            if res_data.get("Response") == "True":
                                data = res_data
                    except Exception:
                        pass
            # --- TIER 5: Fallback to direct public IMDb Autocomplete API suggestions if OMDb fails/limit reached ---
            if not data or data.get("Response") != "True":
                try:
                    query_clean = "".join(c for c in title if c.isalnum() or c.isspace()).strip()
                    if query_clean:
                        query_encoded = urllib.parse.quote(query_clean.lower())
                        first_char = query_encoded[0]
                        url = f"https://v3.sg.media-imdb.com/suggestion/{first_char}/{query_encoded}.json"
                        response = requests.get(url, timeout=5)
                        if response.status_code == 200:
                            suggestions = response.json().get("d", [])
                            match = None
                            for item in suggestions:
                                if item.get("qid") in ("movie", "feature"):
                                    match = item
                                    break
                            if not match and suggestions:
                                match = suggestions[0]
                            if match:
                                imdb_id = match.get("id")
                                data = {
                                    "Response": "True",
                                    "Title": match.get("l"),
                                    "Year": str(match.get("y", "")),
                                    "imdbRating": "N/A",
                                    "imdbID": imdb_id,
                                    "Genre": "",
                                    "Plot": "",
                                    "Poster": match.get("i", {}).get("imageUrl", "") if match.get("i") else ""
                                }
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