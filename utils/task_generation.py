import os
import json
import random
import re
from datetime import datetime, timedelta
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY environment variable not set. Please set it in your .env file or environment.")

client = Groq(api_key=api_key)

def generate_dynamic_coding_tasks(summary: str) -> str:
    """
    Dynamically generates coding tasks with sequential dates in JSON format, based on a project summary,
    guided by project management principles and ISO 21502 compliance.

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

    # --- Initial Task Generation Prompt ---
    prompt = f"""
    Based on the following project summary, generate exactly {num_tasks} coding tasks in a valid JSON format.
    The tasks should represent a logical breakdown of the project work, adhering to good project management practices (similar to concepts in ISO 21502 like Work Breakdown Structure and activity sequencing).

    **Project Summary:**
    {summary}

    **Rules for Task Generation:**
    1. **Action-Oriented Titles:** Each `Task Title` must start with an action verb (e.g., "Implement", "Create", "Design", "Test", "Configure", "Refactor", "Document").
    2. **Clear Descriptions:** The `Task Description` must clearly state the specific action to be performed and the primary outcome or deliverable expected.
    3. **Manageable Scope:** Each task should represent a distinct piece of work logically achievable within the estimated duration. Avoid tasks that are too broad or too trivial.
    4. **Relevance:** All generated tasks must directly contribute to fulfilling the requirements outlined in the **Project Summary**.
    5. **Logical Sequence:** Ensure the sequence of tasks presented in the JSON object follows a logical progression where possible (e.g., setup before implementation, implementation before testing).
    6. **Duration Estimate:** Provide an `Estimated Duration (days)` as an integer, estimated based on the complexity and scope of the task.

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
    }}

    **Start Date for Planning:** {base_date.strftime('%Y-%m-%d')} (Note: You only need to provide the duration; the dates will be calculated later by external code.)
    """

    try:
        print(f"Requesting {num_tasks} tasks from LLM...")
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.6
        )

        tasks_json_string = completion.choices[0].message.content
        print("LLM Response Received.")

        # Robust JSON Extraction
        match = re.search(r'```(?:json)?\s*({.*?})\s*```', tasks_json_string, re.DOTALL | re.IGNORECASE)
        if match:
            valid_json_string = match.group(1)
            print("JSON extracted using regex (markdown fences found).")
        else:
            start_index = tasks_json_string.find('{')
            end_index = tasks_json_string.rfind('}')
            if start_index != -1 and end_index != -1 and start_index < end_index:
                valid_json_string = tasks_json_string[start_index:end_index + 1]
                print("JSON extracted using find method (no markdown fences).")
            else:
                if tasks_json_string.strip().startswith('{') and tasks_json_string.strip().endswith('}'):
                    valid_json_string = tasks_json_string.strip()
                    print("Assuming entire response is JSON.")
                else:
                    print(f"Raw LLM Response:\n---\n{tasks_json_string}\n---")
                    raise ValueError("Could not find a valid JSON structure in the LLM response.")

        tasks_dict = json.loads(valid_json_string)
        print("JSON Parsing Successful.")

        # Calculate Sequential Dates for Initial Tasks
        current_date = base_date
        processed_tasks = {}
        print("Processing initial tasks and calculating dates...")
        for title, details in tasks_dict.items():
            if not isinstance(details, dict):
                print(f"Warning: Skipping task '{title}' because its value is not a dictionary: {details}")
                continue
            duration = details.get("Estimated Duration (days)")
            if not isinstance(duration, int) or duration <= 0:
                duration = 1
                details["Estimated Duration (days)"] = duration
                print(f"Warning: Task '{title}' had invalid/missing duration. Defaulted to {duration} day(s).")
            details["Date"] = current_date.strftime('%Y-%m-%d')
            processed_tasks[title] = details
            current_date += timedelta(days=duration)

        tasks_json = json.dumps(processed_tasks, indent=2)
        print("Initial task processing complete.")

        # --- ISO 21502 Evaluation ---
        print("Evaluating tasks for ISO 21502 compliance...")
        eval_prompt = f"""
        You are an expert in ISO 21502 project management principles. Evaluate the following tasks for a project with the given summary to ensure they adhere to ISO 21502 guidelines, including Work Breakdown Structure (WBS), logical sequencing, and completeness.

        **Project Summary:**
        {summary}

        **Generated Tasks:**
        {tasks_json}

        **Evaluation Rules:**
        1. **Work Breakdown Structure (WBS):** Ensure tasks are broken down into manageable, distinct units of work that collectively cover the project scope.
        2. **Logical Sequencing:** Check that tasks follow a logical order (e.g., setup before implementation, implementation before testing).
        3. **Completeness:** Verify that all necessary tasks to achieve the project objectives are included (e.g., no missing critical tasks like testing, documentation, or deployment).
        4. **Clarity and Specificity:** Ensure task titles and descriptions are clear, action-oriented, and specific.
        5. **Duration Appropriateness:** Check that estimated durations are reasonable for the task scope and complexity, with no fixed range constraint.

        **Output Format:**
        Return a JSON object with the following structure:
        {{
          "is_compliant": boolean,
          "issues": [
            {{
              "issue": string,
              "affected_task": string
            }}
          ],
          "suggested_changes": string
        }}
        """

        eval_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": eval_prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.5
        )

        eval_response = eval_completion.choices[0].message.content
        match = re.search(r'```(?:json)?\s*({.*?})\s*```', eval_response, re.DOTALL | re.IGNORECASE)
        if match:
            eval_json = json.loads(match.group(1))
        else:
            eval_json = json.loads(eval_response.strip())

        print("Evaluation complete.")

        # If compliant, return initial tasks
        if eval_json.get("is_compliant", True):
            print("Tasks are ISO 21502 compliant. Returning initial tasks.")
            return tasks_json

        # --- Task Regeneration if Not Compliant ---
        print("Issues found. Regenerating tasks...")
        issues = eval_json.get("issues", [])
        suggestions = eval_json.get("suggested_changes", "")

        regen_prompt = f"""
        Based on the following project summary, generate coding tasks in a valid JSON format to fully cover the project scope, addressing the issues identified during an ISO 21502 evaluation. The number of tasks may differ from the initial {num_tasks}, there could be more if deemed so, to ensure completeness and compliance, as judged.

        **Project Summary:**
        {summary}

        **Previous Issues:**
        {json.dumps(issues, indent=2)}

        **Suggested Changes:**
        {suggestions}

        **Rules for Task Generation:**
        1. **Action-Oriented Titles:** Each `Task Title` must start with an action verb (e.g., "Implement", "Create", "Design", "Test").
        2. **Clear Descriptions:** The `Task Description` must clearly state the specific action and expected outcome.
        3. **Manageable Scope:** Each task should be achievable within the estimated duration.
        4. **Relevance:** Tasks must contribute to the project requirements.
        5. **Logical Sequence:** Ensure tasks follow a logical progression.
        6. **Duration Estimate:** Provide an integer `Estimated Duration (days)` based on the complexity and scope of the task, with no fixed range constraint.

        **Output Format:**
        Return only a valid JSON object mapping task titles to their details:
        {{
          "Configure Version Control (Git)": {{
            "Task Description": "Initialize Git repository, set up remote origin, and define branching strategy.",
            "Estimated Duration (days)": 1
          }}
        }}

        **Start Date for Planning:** {base_date.strftime('%Y-%m-%d')}
        """

        regen_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": regen_prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.6
        )

        regen_tasks_json = regen_completion.choices[0].message.content
        match = re.search(r'```(?:json)?\s*({.*?})\s*```', regen_tasks_json, re.DOTALL | re.IGNORECASE)
        if match:
            valid_json_string = match.group(1)
        else:
            valid_json_string = regen_tasks_json.strip()

        regen_tasks_dict = json.loads(valid_json_string)

        # Calculate Sequential Dates for Regenerated Tasks
        current_date = base_date
        processed_tasks = {}
        print("Processing regenerated tasks and calculating dates...")
        for title, details in regen_tasks_dict.items():
            if not isinstance(details, dict):
                continue
            duration = details.get("Estimated Duration (days)", 1)
            if not isinstance(duration, int) or duration <= 0:
                duration = 1
                details["Estimated Duration (days)"] = duration
            details["Date"] = current_date.strftime('%Y-%m-%d')
            processed_tasks[title] = details
            current_date += timedelta(days=duration)

        print("Task regeneration complete.")
        return json.dumps(processed_tasks, indent=2)

    except json.JSONDecodeError as e:
        print(f"Raw LLM Response likely causing error:\n---\n{tasks_json_string}\n---")
        raise ValueError(f"Failed to parse valid JSON from Groq response. Error: {e}. Check raw response above.") from e
    except AttributeError as e:
        print(f"Unexpected API response format. Error: {e}. Raw response object:\n---\n{completion}\n---")
        raise ValueError("Unexpected response structure from Groq API.") from e
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise e
    

if __name__ == "__main__":
    # Example project summary
    project_summary = """
    Create a Python-based web application using the Flask framework.
    The application should allow users to register, log in, and create/manage simple text notes.
    Notes should be stored in a PostgreSQL database.
    The user interface should be clean and responsive, built using basic HTML, CSS, and potentially a lightweight CSS framework like Bootstrap.
    Include basic testing for core functionalities.
    """

    print("--- Generating Coding Tasks ---")
    try:
        generated_tasks_json = generate_dynamic_coding_tasks(project_summary)
        print("\n--- Generated Tasks (JSON) ---")
        print(generated_tasks_json)
        print("\n--- Task Generation Successful ---")
    except ValueError as e:
        print(f"\n--- Error During Task Generation ---")
        print(f"An error occurred: {e}")
    except Exception as e:
        print(f"\n--- An Unexpected System Error Occurred ---")
        print(f"Error details: {e}")