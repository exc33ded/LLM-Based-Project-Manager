import os
import google.generativeai as genai
from dotenv import load_dotenv
from PyPDF2 import PdfReader
import json
import re

# Load environment variables and configure GenAI
load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=api_key)

# Define generation configuration
generation_config = {
    'temperature': 0.2,
    'top_p': 0.8,
    'top_k': 64,
    'max_output_tokens': 8192
}

# Initialize the GenerativeModel
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config
)

def read_pdf_raw(file_path):
    """Reads the content of the PDF file."""
    try:
        reader = PdfReader(file_path)
        content = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                content += text + "\n"
        return content.strip()
    except Exception as e:
        return ""

def analyze_synopsis(file_path):
    """Analyzes the project synopsis PDF and returns the parsed JSON result."""
    try:
        # Read the content from the PDF
        pdf_content = read_pdf_raw(file_path)

        if not pdf_content:
            return {"error": "No content found in the PDF."}

        # Upload the PDF to GenAI
        sample_file = genai.upload_file(path=file_path, display_name='Project Synopsis')

        # Prompt to return strict JSON
        prompt = (
            "I have uploaded a project synopsis document. Analyze the document and provide a valid JSON object "
            "with the following keys:\n\n"
            "- 'summary': A concise and comprehensive paragraph summarizing the project, focusing on:\n"
            "  - The project's name and core objective.\n"
            "  - Key functional and non-functional requirements.\n"
            "  - Target users or beneficiaries.\n"
            "  - Any unique or standout features.\n\n"
            "- 'categories': A list of applicable project categories. Choose from:\n"
            "  ['Software Development', 'Web Development', 'Data Science', 'Artificial Intelligence', 'Cybersecurity', "
            "'IoT (Internet of Things)', 'Mobile App Development', 'Other']\n\n"
            "- 'technologies': A list of programming languages, frameworks, or technologies mentioned in the document.\n\n"
            "Output only a valid JSON object with these keys and no additional text."
        )

        # Generate content using the model
        response = model.generate_content([sample_file, prompt])

        # Extract JSON from the response using regex
        json_match = re.search(r"```json\n(.*?)\n```", response.text, re.DOTALL)
        if not json_match:
            return {"error": "Failed to extract JSON from the response."}

        json_content = json_match.group(1).strip()

        # Parse the extracted JSON
        result = json.loads(json_content)

        # Return the parsed result
        return json.dumps(result, indent=4)

    except Exception as e:
        return {"error": f"An error occurred while analyzing the synopsis: {e}"}

# Example usage
if __name__ == "__main__":
    file_path = r"E:\Projects\MINI3\Documentation\Advanced Project Manager for AMU - SRS.pdf"
    result = analyze_synopsis(file_path)
    print("Analysis Result (JSON):")
    print(result)
