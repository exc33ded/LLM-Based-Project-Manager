import os
import json
import random
import re # Import regex module
from datetime import datetime, timedelta
from groq import Groq
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY environment variable not set. Please set it in your .env file or environment.")

# Initialize Groq Client
client = Groq(api_key=api_key)

def generate_dynamic_coding_tasks(summary: str) -> str:
    """
    Dynamically generates between 10 and 15 coding tasks with sequential dates
    in JSON format, based on a project summary, guided by project management principles
    and specific rules.

    Parameters:
        summary (str): The project summary to generate tasks for.

    Returns:
        str: JSON string representing the structured list of tasks with titles,
             descriptions, estimated durations, and calculated sequential dates.

    Raises:
        ValueError: If the GROQ_API_KEY is not set, if the API response cannot be
                    parsed as JSON, or if the response format is unexpected.
        Exception: Catches other potential errors during API call or processing.
    """
    base_date = datetime.today()
    num_tasks = random.randint(10, 15)

    # --- Refined Prompt with Explicit Rules ---
    prompt = f"""
    Based on the following project summary, generate exactly {num_tasks} coding tasks in a valid JSON format.
    The tasks should represent a logical breakdown of the project work, adhering to good project management practices (similar to concepts in ISO 21502 like Work Breakdown Structure and activity sequencing).

    **Project Summary:**
    {summary}

    **Rules for Task Generation:**
    1.  **Action-Oriented Titles:** Each `Task Title` must start with an action verb (e.g., "Implement", "Create", "Design", "Test", "Configure", "Refactor", "Document").
    2.  **Clear Descriptions:** The `Task Description` must clearly state the specific action to be performed and the primary outcome or deliverable expected.
    3.  **Manageable Scope:** Each task should represent a distinct piece of work logically achievable within the estimated duration. Avoid tasks that are too broad or too trivial.
    4.  **Relevance:** All generated tasks must directly contribute to fulfilling the requirements outlined in the **Project Summary**.
    5.  **Logical Sequence:** Ensure the sequence of tasks presented in the JSON object follows a logical progression where possible (e.g., setup before implementation, implementation before testing).
    6.  **Duration Estimate:** Provide an `Estimated Duration (days)` as an integer between 1 and 5 for each task.

    **Output Format:**
    Strictly output *only* a valid JSON object. Do not include any introductory text, explanations, comments, or markdown formatting like ```json ... ``` outside the JSON structure itself. The JSON object must map task titles (as keys) to their details (as values).

    **Example JSON Structure:**
    {{
      "Configure Version Control (Git)": {{
        "Task Description": "Initialize Git repository, set up remote origin, and define branching strategy.",
        "Estimated Duration (days)": 1
      }},
      "Develop User Authentication Module": {{
        "Task Description": "Implement user registration, login, and session management functionality.",
        "Estimated Duration (days)": 4
      }}
      // ... continue for all {num_tasks} tasks
    }}

    **Start Date for Planning:** {base_date.strftime('%Y-%m-%d')} (Note: You only need to provide the duration; the dates will be calculated later by external code.)
    """

    # API call to Groq
    try:
        print(f"Requesting {num_tasks} tasks from LLM...") # Info message
        completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile", # Recommended model, adjust if needed
            temperature=0.6, # Slightly increased temperature for a bit more variation
            # stream=False # Ensure non-streaming for easier JSON extraction initially
        )

        # Get the response content
        tasks_json_string = completion.choices[0].message.content
        print("LLM Response Received.") # Info message

        # --- Robust JSON Extraction ---
        # Try to find the JSON block using regex, handling potential markdown fences
        match = re.search(r'```(?:json)?\s*({.*?})\s*```', tasks_json_string, re.DOTALL | re.IGNORECASE)
        if match:
            valid_json_string = match.group(1)
            print("JSON extracted using regex (markdown fences found).")
        else:
            # If no markdown fences, try finding the first '{' and last '}'
            start_index = tasks_json_string.find('{')
            end_index = tasks_json_string.rfind('}')
            if start_index != -1 and end_index != -1 and start_index < end_index:
                 valid_json_string = tasks_json_string[start_index:end_index + 1]
                 print("JSON extracted using find method (no markdown fences).")
            else:
                # If still not found, maybe the entire string is the JSON
                if tasks_json_string.strip().startswith('{') and tasks_json_string.strip().endswith('}'):
                     valid_json_string = tasks_json_string.strip()
                     print("Assuming entire response is JSON.")
                else:
                    print(f"Raw LLM Response:\n---\n{tasks_json_string}\n---")
                    raise ValueError("Could not find a valid JSON structure in the LLM response.")

        # Convert the JSON string to a Python dictionary
        tasks_dict = json.loads(valid_json_string)
        print("JSON Parsing Successful.") # Info message

        # --- Calculate Sequential Dates and Finalize Structure ---
        current_date = base_date
        processed_tasks = {} # Create a new dict to store processed tasks in order

        print("Processing tasks and calculating dates...") # Info message
        for title, details in tasks_dict.items():
            # Ensure details is a dictionary
            if not isinstance(details, dict):
                 print(f"Warning: Skipping task '{title}' because its value is not a dictionary: {details}")
                 continue

            # Ensure duration is present and valid
            duration = details.get("Estimated Duration (days)")
            if not isinstance(duration, int) or duration <= 0:
                duration = 1 # Default to 1 day if missing or invalid
                details["Estimated Duration (days)"] = duration # Update dict with default
                print(f"Warning: Task '{title}' had invalid/missing duration. Defaulted to {duration} day(s).")

            # Add the calculated date (Format: YYYY-MM-DD)
            details["Date"] = current_date.strftime('%Y-%m-%d')

            # Add the task to the processed dictionary (maintains order if Python >= 3.7)
            processed_tasks[title] = details

            # Increment the date for the next task START date
            current_date += timedelta(days=duration)

        print("Task processing complete.") # Info message
        # Return the processed tasks as a formatted JSON string
        return json.dumps(processed_tasks, indent=2)

    except json.JSONDecodeError as e:
        print(f"Raw LLM Response likely causing error:\n---\n{tasks_json_string}\n---")
        raise ValueError(f"Failed to parse valid JSON from Groq response. Error: {e}. Check raw response above.") from e
    except AttributeError as e:
         # Handle cases where the API response structure might be unexpected (e.g., choices[0] doesn't exist)
         print(f"Unexpected API response format. Error: {e}. Raw response object:\n---\n{completion}\n---")
         raise ValueError("Unexpected response structure from Groq API.") from e
    except Exception as e:
         # Catch other potential errors (e.g., network issues, API key errors from Groq)
         print(f"An unexpected error occurred: {e}")
         raise e # Re-raise the exception after printing


# --- Example Usage ---
# if __name__ == "__main__":
#     # Example project summary
#     project_summary = """
#     Create a Python-based web application using the Flask framework.
#     The application should allow users to register, log in, and create/manage simple text notes.
#     Notes should be stored in a PostgreSQL database.
#     The user interface should be clean and responsive, built using basic HTML, CSS, and potentially a lightweight CSS framework like Bootstrap.
#     Include basic testing for core functionalities.
#     """

#     print("--- Generating Coding Tasks ---")
#     try:
#         generated_tasks_json = generate_dynamic_coding_tasks(project_summary)
#         print("\n--- Generated Tasks (JSON) ---")
#         print(generated_tasks_json)
#         print("\n--- Task Generation Successful ---")
#     except ValueError as e:
#         print(f"\n--- Error During Task Generation ---")
#         print(f"An error occurred: {e}")
#     except Exception as e:
#         print(f"\n--- An Unexpected System Error Occurred ---")
#         print(f"Error details: {e}")