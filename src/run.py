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
    
    # Construct the goal referencing the websites and formatting rules
    goal = GOAL + '\n' + str(websites)
    print("Starting agent loop...")
    final_answer = run_agent_loop(goal)
    
    print("\n--- Final Agent Response ---")
    print(final_answer)
