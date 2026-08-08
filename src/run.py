from prompts.prompts import GOAL
import sys
import os
import json
import io

# Force stdout/stderr to use UTF-8 encoding to avoid Windows console UnicodeEncodeErrors (e.g., with Hebrew text)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add root folder to python path so we can import src.*
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.agent_loop import run_agent_loop
from src.prompts.prompts import GOAL

if __name__ == "__main__":
    # Read the list of websites from websites.json
    websites_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "websites.json")
    with open(websites_file, "r") as f:
        websites = json.load(f)
        
    print(f"Loaded {len(websites)} website(s) to scrape: {websites}\n")
    
    for website in websites:
        print(f"--- Starting agent loop for {website} ---")
        goal = GOAL + '\n' + str([website])
        
        # Retry loop to handle API rate limits and connection errors
        max_retries = 5
        for attempt in range(max_retries):
            final_answer = run_agent_loop(goal)
            
            if final_answer and "Error:" not in str(final_answer):
                break
                
            print(f"Attempt {attempt + 1} failed for {website}. Retrying in 60 seconds...")
            import time
            time.sleep(60)
        
        print(f"\n--- Final Agent Response for {website} ---")
        print(final_answer)
        print("\n" + "="*50 + "\n")
        
        # Add a delay between websites to prevent rate limiting
        if website != websites[-1]:
            print("Waiting 60 seconds before processing the next website to avoid API rate limits...")
            import time
            time.sleep(60)
                    
    print("Cleaning up past screenings from the database...")
    try:
        from supabase import create_client
        from dotenv import load_dotenv
        import datetime
        
        load_dotenv()
        url = os.environ.get("SUPABASE_PROJECT_URL")
        key = os.environ.get("SUPABASE_KEY")
        
        if url and key:
            sb = create_client(url, key)
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            sb.table("screenings").delete().lt("date", today_str).execute()
            print(f"Cleanup complete. Deleted old screenings before {today_str}.")
    except Exception as e:
        print(f"Cleanup failed: {e}")
