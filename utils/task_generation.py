import os
import json
import random
from datetime import datetime, timedelta
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("GROQ_API_KEY")

def generate_dynamic_coding_tasks(summary):
    """
    Dynamically generates between 10 and 15 coding tasks with sequential dates in JSON format, based on a project summary.
    
    Parameters:
        summary (str): The project summary to generate tasks for.
        
    Returns:
        dict: JSON object with task titles, descriptions, and sequential dates.
    """
    client = Groq(
    api_key=os.environ.get("GROQ_API_KEY"),
)

    # Define the base date as today's date
    base_date = datetime.today()
    num_tasks = random.randint(10, 15)  # Random number of tasks between 10 and 15

    # Generate the OpenAI prompt
    prompt = f"""
    Based on the following project summary, generate {num_tasks} coding tasks in valid JSON format.
    Each task should include:
    - A clear task title.
    - A concise task description.
    - An estimated time in days to complete each task (between 1 and 5 days).
    - A sequential date starting from the base date, calculated using the estimated time for the previous task.

    **Project Summary:**  
    {summary}
    
    **Start Date:** {base_date.strftime('%Y-%m-%d')}
    **Output Format:**
    {{
      "Task Title 1": {{
        "Task Description": "Description of Task 1.",
        "Duration (days)": 3,
        "Date": "YYYY-MM-DD"
      }},
      "Task Title 2": {{
        "Task Description": "Description of Task 2.",
        "Duration (days)": 2,
        "Date": "YYYY-MM-DD"
      }}
      // Continue for all tasks.
    }}
    """

    # API call
    completion = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": f"{prompt}",
        }
    ],
    model="llama-3.3-70b-versatile",
    stream=True,
)

    # Collect the response
    tasks_json = ""
    for chunk in completion:
        if chunk.choices[0].delta.content is not None:
            tasks_json += chunk.choices[0].delta.content

    # Extract valid JSON part from the response
    try:
        # Locate the start and end of the JSON block
        start_index = tasks_json.find('{')
        end_index = tasks_json.rfind('}') + 1
        valid_json = tasks_json[start_index:end_index]

        # Convert the JSON string to a Python dictionary
        tasks = json.loads(valid_json)

        # Sequentially adjust dates based on durations
        current_date = base_date
        for task in tasks.values():
            duration = task.get("Duration (days)", random.randint(1, 5))
            task["Date"] = current_date.strftime('%Y-%m-%d')
            current_date += timedelta(days=duration)
            task.pop("Duration (days)", None)  # Remove 'Duration (days)' from the final JSON

        return json.dumps(tasks, indent=2)
    except (json.JSONDecodeError, ValueError, TypeError):
        raise ValueError("Failed to parse valid JSON from OpenAI response.")

# Example usage
# summary_text = "This project involves building a web-based project manager application with an integrated AI assistant."
# tasks = generate_dynamic_coding_tasks(summary_text)
# print(tasks)
