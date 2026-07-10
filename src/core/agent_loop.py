import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from src.prompts.prompts import SYSTEM_PROMPT
from src.core.tools import scrape_cinema_page, search_imdb_data, save_screenings_to_db

# Load environment variables from .env
load_dotenv()

# The SDK automatically uses the GEMINI_API_KEY environment variable when api_key is not specified
client = genai.Client()

def run_agent_loop(user_goal: str):
    # Pass the system prompt through configuration and enable automatic function calling
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[scrape_cinema_page, search_imdb_data, save_screenings_to_db],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False),
        temperature=0.0
    )
    
    print(f"Starting agent with goal: {user_goal}")
    
    try:
        # Initialize conversation history with the user's goal via a Chat session
        # The Chat session handles state and multiple turns of tool calling automatically
        chat = client.chats.create(
            model='gemini-2.5-flash',
            config=config
        )
        
        # Send the message and let the SDK handle the tools
        response = chat.send_message(user_goal)
        
        print("\nGoal Achieved!")
        return response.text
        
    except Exception as e:
        print(f"Agent encountered an error: {e}")
        return f"Error: {e}"