import json
import os
from dotenv import load_dotenv
from google import genai
from src.prompts.system_prompt import SYSTEM_PROMPT
from src.core.tools import TOOL_MANIFEST

# Load environment variables from .env
load_dotenv()

# The SDK automatically uses the GEMINI_API_KEY environment variable when api_key is not specified
client = genai.Client()

def run_agent_loop(user_goal: str):
    # Initialize conversation memory with system rules and user intent
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_goal}
    ]
    
    max_iterations = 10
    for iteration in range(max_iterations):
        # 1. Ask the LLM for its next thought and action
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=str(messages), # Passing historical context
        )
        
        # 2. Parse the structured output
        try:
            decision = json.loads(response.text)
        except json.JSONDecodeError:
            print("Failed to parse agent response as JSON. Retrying with correction nudge...")
            messages.append({"role": "user", "content": "Your last response was not valid JSON. Please repeat using the exact JSON schema requested."})
            continue

        print(f"\n[Iteration {iteration}] Thought: {decision.get('thought')}")
        
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
            messages.append({
                "role": "user", 
                "content": f"Observation from tool [{tool_name}]: {str(tool_output)}"
            })
        else:
            messages.append({
                "role": "user", 
                "content": f"Error: Tool '{tool_name}' does not exist. Choose from available tools."
            })
            
    print("Agent exceeded max iterations without reaching a conclusion.")