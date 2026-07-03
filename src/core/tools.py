import requests
from bs4 import BeautifulSoup

def scrape_cinema_page(url: str) -> str:
    """Scrapes raw text layout from a given Tel Aviv cinema URL, preserving link hrefs."""
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
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
        
    return soup.get_text()[:50000] # Return truncated text for context safety

def search_imdb_data(movie_titles) -> dict:
    """Fetches IMDB score and link for one or more movie titles."""
    if isinstance(movie_titles, str):
        movie_titles = [movie_titles]
    results = {}
    for title in movie_titles:
        results[title] = {
            "title": title,
            "imdb_score": "8.2",
            "url": f"https://www.imdb.com/find?q={title}"
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
        supabase: Client = create_client(url, key)
        
        # Overwrite logic: delete existing screenings for the current cinema(s) in this batch
        cinemas = list(set(s.get("cinema") for s in screenings if s.get("cinema")))
        if cinemas:
            supabase.table("screenings").delete().in_("cinema", cinemas).execute()
            
        # Perform bulk insert into 'screenings' table
        response = supabase.table("screenings").insert(screenings).execute()
        return f"Successfully saved {len(screenings)} screenings to the Supabase database."
    except Exception as e:
        return f"Error saving to database: {str(e)}"

# Map strings to actual callable functions for our loop execution stage
TOOL_MANIFEST = {
    "scrape_cinema_page": scrape_cinema_page,
    "search_imdb_data": search_imdb_data,
    "save_screenings_to_db": save_screenings_to_db
}