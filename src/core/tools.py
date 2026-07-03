import requests
from bs4 import BeautifulSoup

def scrape_cinema_page(url: str) -> str:
    """Scrapes raw text layout from a given Tel Aviv cinema URL."""
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    # Strip scripts/styles to save token window
    for script in soup(["script", "style"]):
        script.extract()
    return soup.get_text()[:4000] # Return truncated text for context safety

def search_imdb_data(movie_title: str) -> dict:
    """Fetches IMDB score and link for a specific movie title via a free API or search scraping."""
    # Placeholder for your implementation (e.g., OMDb API or rapidapi)
    return {
        "title": movie_title,
        "imdb_score": "8.2",
        "url": f"https://www.imdb.com/find?q={movie_title}"
    }

# Map strings to actual callable functions for our loop execution stage
TOOL_MANIFEST = {
    "scrape_cinema_page": scrape_cinema_page,
    "search_imdb_data": search_imdb_data
}