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
                        val_cleaned = BeautifulSoup(str(val), 'html.parser').get_text(separator='\n').strip()
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
    from urllib.parse import urljoin, unquote
    for a in soup.find_all('a', href=True):
        link_text = a.get_text().strip()
        link_url = a['href']
        # Resolve relative URLs
        if link_url.startswith('/') or not link_url.startswith('http'):
            link_url = urljoin(url, link_url)
        # Unquote URL so it is clean, human-readable Hebrew characters (e.g. /event/האישה-שלא-ידעה-לאהוב-נבחרי-דוקאביב/)
        link_url = unquote(link_url)
        a.replace_with(f" [{link_text}]({link_url}) ")
        
    # Replace image tags with ![alt](src) to preserve movie posters for fallback
    for img in soup.find_all('img'):
        alt_text = img.get('alt', '').strip() or 'Poster'
        # Check lazy-loading data attributes first (common on WordPress / Cinematheque sites)
        img_url = (
            img.get('data-src') or 
            img.get('data-lazy-src') or 
            img.get('data-original') or 
            img.get('src') or 
            ''
        ).strip()
        
        # Skip 1x1 placeholder base64 gifs or empty URLs
        if not img_url or img_url.startswith('data:image/gif') or img_url == 'data:,':
            continue
            
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

def search_imdb_autocomplete(query: str, release_year: str = None) -> str:
    """Queries the IMDb public autocomplete suggestion endpoint and returns the best matching imdbID."""
    import requests
    import urllib.parse
    import re
    import difflib
    
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
            if not results:
                return None
                
            def normalize_title(t):
                return re.sub(r'[^a-z0-9]', '', str(t).lower())
                
            norm_query = normalize_title(query)
            
            # 1. Exact normalized title match
            exact_matches = []
            for item in results:
                title_cand = item.get("l", "")
                if normalize_title(title_cand) == norm_query:
                    exact_matches.append(item)
                    
            if exact_matches:
                if release_year:
                    for item in exact_matches:
                        if str(item.get("y", "")) == str(release_year):
                            return item.get("id")
                for item in exact_matches:
                    if item.get("qid") in ("movie", "feature"):
                        return item.get("id")
                return exact_matches[0].get("id")
                
            # 2. Sequence similarity match
            best_id = None
            best_score = -1.0
            for item in results:
                title_cand = item.get("l", "")
                ratio = difflib.SequenceMatcher(None, norm_query, normalize_title(title_cand)).ratio()
                if item.get("qid") in ("movie", "feature"):
                    ratio += 0.05
                if release_year and str(item.get("y", "")) == str(release_year):
                    ratio += 0.1
                if ratio > best_score:
                    best_score = ratio
                    best_id = item.get("id")
                    
            return best_id
    except Exception as e:
        print(f"IMDb Autocomplete error for '{query}': {e}")
    return None

def search_imdb_data(movie_titles: list[str], b64_posters: bool = False) -> dict:
    """Fetches movie metadata (IMDb url/score, RT score, Poster, Plot, Year) from OMDb API for movie titles."""
    import requests
    import os
    import re
    import urllib.parse
    import json
    
    if isinstance(movie_titles, str):
        movie_titles = [movie_titles]
        
    api_key = os.environ.get("OMDB_KEY")
    results = {}
    
    # Load local cache if available
    cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "imdb_cache.json")
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass
            
    titles_to_query = []
    for title in movie_titles:
        if title in cache and cache[title].get("imdb_url") and "find?q=" not in cache[title].get("imdb_url", ""):
            results[title] = cache[title]
        else:
            titles_to_query.append(title)
            
    if not titles_to_query:
        return results
        
    if not api_key:
        for title in titles_to_query:
            results[title] = {
                "imdb_url": f"https://www.imdb.com/find?q={title}",
                "imdb_score": "N/A",
                "rt_score": "N/A",
                "poster_url": "",
                "plot": "",
                "year": ""
            }
        return results
        
    def is_hebrew(text: str) -> bool:
        hebrew_chars = [c for c in text if 1424 <= ord(c) <= 1514]
        alpha_chars = [c for c in text if c.isalpha()]
        if not alpha_chars: return False
        return len(hebrew_chars) / len(alpha_chars) > 0.5

    for title in titles_to_query:
        if is_hebrew(title):
            results[title] = {
                "imdb_url": f"https://www.imdb.com/find?q={urllib.parse.quote(title)}",
                "imdb_score": "N/A",
                "rt_score": "N/A",
                "poster_url": "",
                "plot": "",
                "year": ""
            }
            continue
            
        try:
            data = None
            imdb_id = None
            
            # --- TIER 0: Manual Overrides for known classic screenings ---
            MANUAL_OVERRIDES = {
                "Aladdin": "tt0103639" # 1992 animated version
            }
            if title in MANUAL_OVERRIDES:
                imdb_id = MANUAL_OVERRIDES[title]
                id_url = f"http://www.omdbapi.com/?apikey={api_key}&i={imdb_id}&plot=full"
                try:
                    response = requests.get(id_url, timeout=5)
                    res_data = response.json()
                    if res_data.get("Response") == "True":
                        data = res_data
                except Exception:
                    pass
            
            # --- TIER 1: Try IMDb Autocomplete first (ranked by popularity/relevance) ---
            if not data or data.get("Response") != "True":
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
                            if suggestions:
                                import difflib
                                norm_query = re.sub(r'[^a-z0-9]', '', title.lower())
                                exact_match = None
                                best_match = None
                                best_score = -1.0
                                
                                for item in suggestions:
                                    title_cand = item.get("l", "")
                                    norm_cand = re.sub(r'[^a-z0-9]', '', title_cand.lower())
                                    if norm_cand == norm_query:
                                        exact_match = item
                                        break
                                    ratio = difflib.SequenceMatcher(None, norm_query, norm_cand).ratio()
                                    if item.get("qid") in ("movie", "feature"):
                                        ratio += 0.05
                                    if ratio > best_score:
                                        best_score = ratio
                                        best_match = item
                                        
                                match = exact_match or best_match or suggestions[0]
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
            
    # Update cache and save to file
    if titles_to_query:
        for title in titles_to_query:
            if title in results:
                cache[title] = results[title]
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
            
    if not b64_posters:
        import copy
        results_clean = copy.deepcopy(results)
        for title, meta in results_clean.items():
            if meta.get("poster_url", "").startswith("data:"):
                meta["poster_url"] = "[Base64 Cached Image]"
        return results_clean
    return results

VALID_CINEMA_EVENT_URLS = set()

def get_valid_cinematheque_urls():
    """Fetches and caches all genuine event URLs from cinema.co.il."""
    global VALID_CINEMA_EVENT_URLS
    if not VALID_CINEMA_EVENT_URLS:
        try:
            import requests
            import urllib.parse
            from bs4 import BeautifulSoup
            r = requests.get('https://www.cinema.co.il/', headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if '/event/' in href:
                        VALID_CINEMA_EVENT_URLS.add(urllib.parse.unquote(href))
        except Exception as e:
            print(f"Error fetching Cinematheque URLs: {e}")
    return VALID_CINEMA_EVENT_URLS

def qa_and_validate_links(screenings: list[dict]):
    """Performs automated parallel link and image QA for each screening to ensure all URLs actually work."""
    import requests
    import urllib.parse
    import difflib
    import concurrent.futures
    
    headers = {"User-Agent": "Mozilla/5.0"}
    
    def process_single_screening(s):
        # 1. QA Ticket URL
        raw_t_url = s.get("ticket_url", "")
        if raw_t_url and raw_t_url.startswith("http"):
            t_url = urllib.parse.unquote(raw_t_url)
            s["ticket_url"] = t_url
            
            try:
                r = requests.head(t_url, headers=headers, timeout=3, allow_redirects=True)
                if r.status_code >= 400:
                    r = requests.get(t_url, headers=headers, timeout=3, stream=True)
                
                # If Cinematheque URL failed, attempt fixing encoding or slug via fuzzy match against site
                if r.status_code >= 400 and "cinema.co.il" in t_url:
                    valid_urls = get_valid_cinematheque_urls()
                    if valid_urls:
                        matches = difflib.get_close_matches(t_url, list(valid_urls), n=1, cutoff=0.5)
                        if matches:
                            s["ticket_url"] = matches[0]
                            print(f"[QA FIXED] ticket_url for {s.get('title')}: {matches[0]}")
            except Exception as e:
                print(f"[QA WARNING] ticket_url check for {s.get('title')}: {e}")

        # 2. QA Poster URL
        p_url = s.get("poster_url", "")
        if p_url and p_url.startswith("http"):
            lower_p = p_url.lower()
            # Immediately catch web pages incorrectly saved as poster_url
            if "/event/" in lower_p or "/pages/" in lower_p or ".aspx" in lower_p or "cintlv.pres.global" in lower_p:
                print(f"[QA STRIPPED] poster_url was webpage HTML for {s.get('title')}: {p_url}")
                s["poster_url"] = ""
                return
                
            try:
                r = requests.head(p_url, headers=headers, timeout=3, allow_redirects=True)
                if r.status_code >= 400:
                    r = requests.get(p_url, headers=headers, timeout=3, stream=True)
                
                if r.status_code >= 400:
                    print(f"[QA STRIPPED] poster_url returned {r.status_code} for {s.get('title')}: {p_url}")
                    s["poster_url"] = ""
                else:
                    ct = r.headers.get("Content-Type", "").lower()
                    if "text/html" in ct and not any(lower_p.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
                        print(f"[QA STRIPPED] poster_url returned HTML content-type for {s.get('title')}: {p_url}")
                        s["poster_url"] = ""
            except Exception as e:
                print(f"[QA WARNING] poster_url check for {s.get('title')}: {e}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        list(executor.map(process_single_screening, screenings))

def save_screenings_to_db(screenings: list[dict]) -> str:
    """Upserts all screenings into the Supabase 'screenings' table and uploads any base64 posters to storage.
    Expects a list of dictionaries, where each dictionary represents a screening.
    Each screening dict can contain: 'title', 'date', 'time', 'cinema', 'year', 'ticket_url',
    and optionally 'plot', 'poster_url', etc.
    """
    from supabase import create_client, Client
    import os
    import json
    
    url = os.environ.get("SUPABASE_PROJECT_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return "Error: Supabase environment variables not found in .env"
        
    try:
        # 1. Clean titles and deduplicate screenings
        unique_screenings = []
        seen = set()
        for s in screenings:
            title = s.get("title", "").strip()
            # Clean up specific titles and typos
            if "Miniions" in title:
                title = title.replace("Miniions", "Minions")
            if "Minions & Monsters" in title or "מיניונים ומפלצות" in title or "Minions and Monsters" in title:
                title = "Minions & Monsters"
            s["title"] = title
            
            # Correct any year errors in the screening date (all current screenings are in 2026)
            date_str = s.get("date", "")
            if date_str:
                if date_str.startswith("2024-") or date_str.startswith("2025-"):
                    date_str = "2026-" + date_str[5:]
                    s["date"] = date_str
            
            # Clean up cinema names
            cinema = s.get("cinema", "")
            if "Cinemateque" in cinema:
                cinema = "Tel-Aviv Cinematheque"
            s["cinema"] = cinema
            
            k = (title, s.get("date"), s.get("time"), cinema)
            if k not in seen:
                seen.add(k)
                unique_screenings.append(s)
        screenings = unique_screenings

        # 2. Extract unique titles and fetch IMDb metadata
        titles = list(set(s.get("title") for s in screenings if s.get("title")))
        imdb_data = search_imdb_data(titles, b64_posters=True)
        
        # 3. Merge metadata with screenings
        for s in screenings:
            title = s.get("title")
            meta = imdb_data.get(title, {})
            
            s["imdb_url"] = meta.get("imdb_url") or s.get("imdb_url") or f"https://www.imdb.com/find?q={title}"
            s["imdb_score"] = meta.get("imdb_score") or s.get("imdb_score") or "N/A"
            s["rt_score"] = meta.get("rt_score") or s.get("rt_score") or "N/A"
            
            year_val = s.get("year")
            if not year_val or year_val in ("N/A", "None", "None"):
                s["year"] = meta.get("year") or s.get("year") or ""
                
            plot_val = s.get("plot")
            if not plot_val or plot_val in ("N/A", "None", ""):
                s["plot"] = meta.get("plot") or s.get("plot") or ""
                
            poster_val = s.get("poster_url")
            if not poster_val or poster_val in ("N/A", "None", "", "[Base64 Cached Image]"):
                s["poster_url"] = meta.get("poster_url") or s.get("poster_url") or ""
                
            # Double check all fields for standard formatting
            for field in ["imdb_score", "rt_score", "plot", "poster_url", "year"]:
                if s.get(field) is None or s.get(field) == "None":
                    s[field] = "N/A" if "score" in field else ""

        # 4. QA and validate ticket and poster URLs
        print(f"Running automated link and poster QA on {len(screenings)} screenings...")
        qa_and_validate_links(screenings)
                    
        # Clean up local screenings.json since we only want to keep imdb_cache.json locally
        output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
        output_path = os.path.join(output_dir, "screenings.json")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass

        # 5. Save to Supabase
        supabase: Client = create_client(url, key)
        
        # Overwrite logic: delete existing screenings for the current cinema(s) in this batch
        cinemas = list(set(s.get("cinema") for s in screenings if s.get("cinema")))
        if cinemas:
            supabase.table("screenings").delete().in_("cinema", cinemas).execute()
            
        # Create a copy for Supabase and upload base64 to Storage to avoid 1MB payload limits
        import copy
        import re
        import base64
        
        def slugify(s_title):
            return re.sub(r'[^a-z0-9]+', '-', s_title.lower()).strip('-')
            
        supabase_screenings = copy.deepcopy(screenings)
        for s in supabase_screenings:
            poster_val = s.get("poster_url", "")
            if poster_val.startswith("data:image"):
                try:
                    header, encoded = poster_val.split(",", 1)
                    ext = header.split(";")[0].split("/")[1] if "/" in header else "jpg"
                    if ext == "jpeg": ext = "jpg"
                    
                    image_data = base64.b64decode(encoded)
                    title_slug = slugify(s.get("title", "poster"))
                    file_name = f"{title_slug}.{ext}"
                    
                    # Try to upload the file to Supabase storage
                    try:
                        supabase.storage.from_("posters").upload(
                            file_name,
                            image_data,
                            {"content-type": f"image/{ext}"}
                        )
                    except Exception:
                        pass # Likely already exists
                        
                    # Retrieve the public URL
                    public_url = supabase.storage.from_("posters").get_public_url(file_name)
                    s["poster_url"] = public_url
                except Exception as e:
                    print(f"Failed to upload poster for {s.get('title')}: {e}")
                    s["poster_url"] = "" # Strip base64 to prevent payload too large errors
        # Perform bulk insert into 'screenings' table
        try:
            res = supabase.table("screenings").insert(supabase_screenings).execute()
            print(f"SUCCESS: Saved {len(res.data)} screenings to the DB.")
            return f"Successfully saved {len(res.data)} screenings to the database!"
        except Exception as e:
            error_msg = f"DB Insert Error: {e}"
            print(error_msg)
            return error_msg
    except Exception as e:
        return f"Error saving to database: {str(e)}"

# Map strings to actual callable functions for our loop execution stage
TOOL_MANIFEST = {
    "scrape_cinema_page": scrape_cinema_page,
    "search_imdb_data": search_imdb_data,
    "save_screenings_to_db": save_screenings_to_db
}