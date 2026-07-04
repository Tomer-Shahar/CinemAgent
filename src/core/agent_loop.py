import json
import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from src.prompts.prompts import SYSTEM_PROMPT
from src.core.tools import TOOL_MANIFEST

# Load environment variables from .env
load_dotenv()

# The SDK automatically uses the GEMINI_API_KEY environment variable when api_key is not specified
client = genai.Client()

def run_agent_loop(user_goal: str):
    # Pass the system prompt through configuration
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json"  # Enforce JSON response matching the prompt schema
    )
    
    # Initialize conversation history with the user's goal
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_goal)]
        )
    ]
    
    max_iterations = 30
    for iteration in range(max_iterations):
        # 1. Ask the LLM for its next thought and action with exponential backoff on 429 rate limits
        retry_delay = 16
        for attempt in range(6):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=contents,
                    config=config,
                )
                break
            except Exception as e:
                status_code = getattr(e, 'status_code', None) or getattr(e, 'code', None)
                is_transient = (
                    status_code in [429, 500, 502, 503, 504] or
                    any(str(code) in str(e) for code in [429, 500, 502, 503, 504]) or
                    "UNAVAILABLE" in str(e)
                )
                if is_transient and attempt < 5:
                    print(f"Transient error encountered ({e}). Waiting {retry_delay} seconds before retry (attempt {attempt + 1}/6)...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    raise e
        
        # 2. Parse the structured output
        try:
            decision = json.loads(response.text)
            if not isinstance(decision, dict):
                raise ValueError("Response is not a JSON object (dict)")
        except (json.JSONDecodeError, ValueError) as err:
            print(f"Failed to parse agent response or response not a dict: {err}. Retrying with correction nudge...")
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=response.text)]))
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text="Your last response was not a valid JSON object matching the requested schema. Please repeat using the exact JSON schema with 'thought', 'action', 'action_input', and 'final_answer' keys.")]))
            continue

        print(f"\n[Iteration {iteration}] Thought: {decision.get('thought')}")
        
        # Record the model's output in the history
        contents.append(types.Content(role="model", parts=[types.Part.from_text(text=response.text)]))
        
        # Check if agent completed the goal
        if decision.get("final_answer"):
            print("\nGoal Achieved!")
            return decision["final_answer"]
        
        # 3. Handle Tool Execution
        tool_name = decision.get("action")
        tool_args = decision.get("action_input", {})
        
        if tool_name in TOOL_MANIFEST:
            print(f"-> Executing Tool [{tool_name}] with args: {tool_args}")
            # Execute the matching Python function dynamically
            tool_output = TOOL_MANIFEST[tool_name](**tool_args)
            
            # 4. Feed the observation back into memory as new context
            contents.append(types.Content(
                role="user", 
                parts=[types.Part.from_text(text=f"Observation from tool [{tool_name}]: {str(tool_output)}")]
            ))
        else:
            contents.append(types.Content(
                role="user", 
                parts=[types.Part.from_text(text=f"Error: Tool '{tool_name}' does not exist. Choose from available tools.")]
            ))
            
    print("Agent exceeded max iterations without reaching a conclusion.")