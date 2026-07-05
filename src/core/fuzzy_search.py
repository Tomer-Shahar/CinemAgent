import requests
import difflib


def fetch_imdb_with_fuzzy_fallback(movie_title: str, api_key: str) -> dict:
    """
    Executes a tiered strategy to resolve messy movie names:
    Tier 1: Try exact OMDb match.
    Tier 2: Try IMDb Autocomplete API for typo-tolerant matching.
    Tier 3: Try OMDb Search endpoint & fuzzy match results locally.
    """
    print(f"Resolving: '{movie_title}'...")
    
    # --- TIER 1: Try OMDb Exact ---
    exact_url = f"http://www.omdbapi.com/?t={movie_title}&apikey={api_key}"
    try:
        res = requests.get(exact_url, timeout=5).json()
        if res.get("Response") == "True":
            print("  [SUCCESS] Tier 1: Exact match found.")
            return {
                "title": res.get("Title"),
                "imdb_score": res.get("imdbRating"),
                "imdb_url": f"https://www.imdb.com/title/{res.get('imdbID')}/",
                "genre": res.get("Genre"),
                "description": res.get("Plot")
            }
    except Exception:
        pass

    # --- TIER 2: Try IMDb Autocomplete fallback ---
    print("  [FALLBACK] Tier 1 failed. Triggering Autocomplete lookup...")
    imdb_id = search_imdb_autocomplete(movie_title)
    if imdb_id:
        print(f"  [SUCCESS] Tier 2: Found IMDb ID '{imdb_id}' via autocomplete.")
        # Retrieve complete metadata by discovered ID instead of title
        id_url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={api_key}"
        try:
            res = requests.get(id_url, timeout=5).json()
            if res.get("Response") == "True":
                return {
                    "title": res.get("Title"),
                    "imdb_score": res.get("imdbRating"),
                    "imdb_url": f"https://www.imdb.com/title/{imdb_id}/",
                    "genre": res.get("Genre"),
                    "description": res.get("Plot")
                }
        except Exception:
            pass

    # --- TIER 3: Try OMDb Search + Local difflib fuzzy selection ---
    print("  [FALLBACK] Tier 2 failed. Attempting OMDb Search matching...")
    search_url = f"http://www.omdbapi.com/?s={movie_title}&apikey={api_key}"
    try:
        search_res = requests.get(search_url, timeout=5).json()
        if search_res.get("Response") == "True":
            search_items = search_res.get("Search", [])
            titles = [item.get("Title") for item in search_items if "Title" in item]
            
            # Fuzzy compare titles to our messy input
            matches = difflib.get_close_matches(movie_title, titles, n=1, cutoff=0.3)
            if matches:
                best_match = matches[0]
                # Find matching record to extract ID
                for item in search_items:
                    if item.get("Title") == best_match:
                        matched_id = item.get("imdbID")
                        print(f"  [SUCCESS] Tier 3: Selected best fuzzy match '{best_match}' ({matched_id}).")
                        
                        id_url = f"http://www.omdbapi.com/?i={matched_id}&apikey={api_key}"
                        res = requests.get(id_url, timeout=5).json()
                        return {
                            "title": res.get("Title"),
                            "imdb_score": res.get("imdbRating"),
                            "imdb_url": f"https://www.imdb.com/title/{matched_id}/",
                            "genre": res.get("Genre"),
                            "description": res.get("Plot")
                        }
    except Exception:
        pass

    return {"error": f"Could not find any matched titles for '{movie_title}'."}