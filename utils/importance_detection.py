import json
import re
from langchain_core.messages import HumanMessage

def detect_important_info_with_ai(chat_model, message, project_summary):
    project_summary = project_summary.replace('{', '{{').replace('}', '}}')
    message = message.replace('{', '{{').replace('}', '}}')

    prompt = f"""
    You are an AI assistant tasked with determining the importance of a message in the context of a student project. 
    The project summary is: "{project_summary}"

    The message to evaluate is: "{message}"

    Instructions:
    1. Analyze the message and decide if it contains important information (e.g., deadlines, tasks, key decisions).
    2. Assign an importance score between 0.0 (not important) and 1.0 (very important).
    3. If important, extract the key content (e.g., a deadline or task). If not, return None for content.
    4. Return your response in JSON format with 'importance_score' and 'important_content' fields.

    Example:
    - Message: "The deadline is April 10."
    - Response: {{"importance_score": 0.9, "important_content": "Deadline: April 10"}}
    - Message: "I like this project."
    - Response: {{"importance_score": 0.2, "important_content": null}}
    """

    response = chat_model.invoke([HumanMessage(content=prompt)]).content
    # print("\n🔍 RAW AI RESPONSE:\n", response)

    # Try to extract the JSON object from the response
    try:
        json_text_match = re.search(r'{.*?}', response, re.DOTALL)
        if json_text_match:
            json_text = json_text_match.group(0)
            result = json.loads(json_text)
            importance_score = float(result.get('importance_score', 0.5))
            important_content = result.get('important_content', None)
            return important_content, importance_score
        else:
            print("❌ No valid JSON object found in the response.")
    except Exception as e:
        print("❌ Failed to parse JSON:", e)

    return None, 0.5
