from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import login_required, current_user
from models import Project, db, Task, User, MiniAdminProject, MiniAdminProjectTask, MiniAdminProjectStudent, LongTermMemory
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import random
from utils.pdf_summarize import analyze_synopsis
from utils.task_generation import generate_dynamic_coding_tasks
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
import markdown
from dotenv import load_dotenv
from utils.no_again_flash import flash_unique
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

load_dotenv()

student_routes = Blueprint('student_routes', __name__)

UPLOAD_FOLDER = 'static/uploads/synopsis'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# LangChain configuration
os.environ["LANGSMITH_TRACING"] = os.environ.get("LANGSMITH_TRACING", "false")
os.environ["LANGSMITH_ENDPOINT"] = os.environ.get("LANGSMITH_ENDPOINT", "")
os.environ["LANGSMITH_API_KEY"] = os.environ.get("LANGSMITH_API_KEY", "")
os.environ["LANGSMITH_PROJECT"] = os.environ.get("LANGSMITH_PROJECT", "")

os.environ["LANGCHAIN_API_KEY"] = os.environ.get("LANGCHAIN_API_KEY", "")
os.environ["GOOGLE_API_KEY"] = os.environ.get("GOOGLE_API_KEY", "")

# Initialize Gemini with advanced configuration
chat_model = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-thinking-exp-01-21",
    temperature=0.7,  # Add some creativity while maintaining accuracy
    top_p=0.8,        # Control response diversity
    top_k=40,         # Limit token selection
    max_output_tokens=1024,  # Allow for detailed responses
    convert_system_message_to_human=True
)

memory_store = {}
archive_memory_store = {}

def render_markdown(content):
    return markdown.markdown(content)

# Buffer memory configuration (keeps the last N messages)
BUFFER_SIZE = 20

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'student':
            flash_unique('Unauthorized access', 'danger', persistent=False)
            return redirect(url_for('auth_routes.login'))
        return f(*args, **kwargs)
    return decorated_function

@student_routes.route('/student/dashboard', methods=['GET', 'POST'])
@login_required
@student_required
def student_dashboard():
    # Get the student's projects
    projects = Project.query.filter_by(student_id=current_user.id).all()

    total_tasks = 0
    completed_tasks = 0
    in_progress_tasks = 0
    backlog_tasks = 0
    progressed_tasks = 0
    project_task_counts = []  # To store task count for each project

    # Calculate task counts for each project
    for project in projects:
        project_tasks = Task.query.filter_by(project_id=project.id).all()
        project_backlog = sum(1 for task in project_tasks if task.status == 'Backlog')
        project_in_progress = sum(1 for task in project_tasks if task.status == 'In Progress')
        project_progressed = sum(1 for task in project_tasks if task.status == 'Progressed')
        project_finished = sum(1 for task in project_tasks if task.status == 'Finished')

        # Store task count for the project
        project_task_counts.append({
            'project': project,
            'backlog': project_backlog,
            'in_progress': project_in_progress,
            'progressed': project_progressed,
            'finished': project_finished
        })

        # Aggregate task counts across all projects
        backlog_tasks += project_backlog
        in_progress_tasks += project_in_progress
        progressed_tasks += project_progressed
        completed_tasks += project_finished
        total_tasks += len(project_tasks)

    # Calculate progress percentage (if any tasks exist)
    progress_percentage = round((completed_tasks / total_tasks * 100), 2) if total_tasks else 0

    # Get upcoming deadlines for the student's projects
    upcoming_deadlines = [(project.title, project.start_date.strftime('%Y-%m-%d')) for project in projects]

    return render_template(
        'student/student_dashboard.html',
        user=current_user,
        greeting=f"Welcome, {current_user.name}!",
        projects=projects,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        in_progress_tasks=in_progress_tasks,
        progress_percentage=progress_percentage,
        upcoming_deadlines=upcoming_deadlines,
        backlog_tasks_count=backlog_tasks,
        progressed_tasks_count=progressed_tasks,
        finished_tasks_count=completed_tasks,
        project_task_counts=project_task_counts  # Pass project-wise task counts
    )


@student_routes.route('/student/projects')
@login_required
@student_required
def view_projects():
    user = User.query.get_or_404(current_user.id)
    projects = Project.query.filter_by(student_id=current_user.id).all()
    return render_template('student/view_projects.html', projects=projects, user=user)

@student_routes.route('/student/projects/add', methods=['GET', 'POST'])
@login_required
@student_required
def add_project():
    if request.method == 'POST':
        title = request.form['title']
        start_date_str = request.form['start_date']
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') 
        synopsis = request.files['synopsis']

        # Validate file type
        if not synopsis.filename.lower().endswith('.pdf'):
            flash("Only PDF files are allowed for synopsis upload.", "danger")
            return redirect(url_for('student_routes.add_project'))

        # Generate a unique filename for the uploaded synopsis
        num = random.randint(1, 10000)
        unique_synopsis_filename = f"{current_user.name}_{current_user.rollno}__{num}__{title}_synopsis.pdf"
        synopsis_filename = secure_filename(unique_synopsis_filename)
        synopsis_path = os.path.join(UPLOAD_FOLDER, synopsis_filename)
        synopsis.save(synopsis_path)

        # Analyze the synopsis using the AI script
        ai_result = analyze_synopsis(synopsis_path)

        # Handle errors during AI analysis
        try:
            ai_data = json.loads(ai_result)
            if "error" in ai_data:
                flash(ai_data["error"], "danger")
                return redirect(url_for('student_routes.add_project'))
        except json.JSONDecodeError:
            flash("Error analyzing synopsis. Please try again.", "danger")
            return redirect(url_for('student_routes.add_project'))

        # Parse AI analysis result
        summary = ai_data.get("summary", "No summary provided.")
        categories = ai_data.get("categories", ["Other"])
        category = ", ".join(categories)

        # Save the project details in the database
        project = Project(
            title=title,
            start_date=start_date,
            synopsis_filename=synopsis_filename,
            student_id=current_user.id,
            summary=summary,
            category=category
        )
        db.session.add(project)
        db.session.commit()

        # Generate tasks based on the summary
        try:
            task_data = json.loads(generate_dynamic_coding_tasks(summary))
            for task_title, task_details in task_data.items():
                new_task = Task(
                    title=task_title,
                    description=task_details["Task Description"],
                    due_date=datetime.strptime(task_details["Date"], '%Y-%m-%d'),
                    status='In Progress',
                    project_id=project.id
                )
                db.session.add(new_task)
            db.session.commit()
        except ValueError or Exception as e:
            flash(f"Task generation failed: {e}", "danger")
            return redirect(url_for('student_routes.view_projects'))

        flash_unique("Project added successfully!", "success", persistent=False)
        return redirect(url_for('student_routes.view_projects'))

    return render_template('student/add_project.html')

@student_routes.route('/student/projects/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
@student_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)

    if project.student_id != current_user.id:
        flash_unique('Unauthorized to edit this project', 'danger', persistent=False)
        return redirect(url_for('student_routes.view_projects'))
    
    category_colors = ['#FFCDD2', '#F8BBD0', '#E1BEE7', '#D1C4E9', '#C5CAE9', '#BBDEFB', '#B3E5FC', '#B2EBF2', '#B2DFDB', '#C8E6C9', '#DCEDC8', '#F0F4C3']

    if request.method == 'POST':
        title = request.form['title']
        start_date_str = request.form['start_date']
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        synopsis = request.files.get('synopsis')
        
        # Update title and start date
        project.title = title
        project.start_date = start_date
        
        # Get the updated categories from the hidden input
        updated_categories = request.form.get('categories', '')  # Capturing the categories
        project.category = updated_categories  # Update the categories field with the new list
        
        # If a new synopsis is uploaded
        if synopsis:
            unique_synopsis_filename = secure_filename(f"{current_user.name}_{current_user.rollno}_{title}_synopsis.{synopsis.filename.split('.')[-1]}")
            synopsis_path = os.path.join(UPLOAD_FOLDER, unique_synopsis_filename)
            synopsis.save(synopsis_path)
            project.synopsis_filename = unique_synopsis_filename
            
            # Analyze the new synopsis
            analysis_result = analyze_synopsis(synopsis_path)
            
            if "error" not in analysis_result:
                analysis_data = json.loads(analysis_result)
                project.summary = analysis_data.get('summary', '')
                project.category = ", ".join(analysis_data.get('categories', []))
            else:
                flash("AI analysis failed: " + analysis_result['error'], "warning")

        db.session.commit()
        flash_unique("Project updated successfully!", "success", persistent=False)
        return redirect(url_for('student_routes.view_projects'))

    return render_template('student/edit_project.html', project=project, category_colors=category_colors)


@student_routes.route('/student/projects/delete/<int:project_id>', methods=['POST'])
@login_required
@student_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)

    if project.student_id != current_user.id:
        flash('Unauthorized to delete this project', 'danger')
        return redirect(url_for('student_routes.view_projects'))

    try:
        if project.synopsis_filename:
            synopsis_path = os.path.join(UPLOAD_FOLDER, project.synopsis_filename)
            if os.path.exists(synopsis_path):
                os.remove(synopsis_path)
                
        LongTermMemory.query.filter_by(project_id=project_id).delete()

        db.session.delete(project)
        db.session.commit()
        memory_store.pop(project_id, None)

        flash_unique("Project and its chat history deleted successfully!", "success", persistent=False)

    except Exception as e:
        db.session.rollback()  
        flash_unique(f"Error deleting project: {str(e)}", "danger", persistent=False)

    return redirect(url_for('student_routes.view_projects'))


def get_archive_chatbot_html():
    """Generate HTML for the archive chatbot UI"""
    # CSS styles for the archive chatbot
    chatbot_styles = """
    <style>
        .archive-chatbot-container {
            border: 1px solid #ddd;
            border-radius: 10px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 500px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        
        .archive-chatbot-header {
            background-color: #f8f9fa;
            padding: 15px;
            border-bottom: 1px solid #ddd;
        }
        
        .archive-chatbot-header h4 {
            margin: 0;
            color: #333;
        }
        
        .archive-chatbot-messages {
            flex: 1;
            overflow-y: auto;
            padding: 15px;
            display: flex;
            flex-direction: column;
            gap: 15px;
            background-color: #f9f9f9;
        }
        
        .archive-bot-message, .archive-user-message {
            max-width: 80%;
            padding: 10px 15px;
            border-radius: 10px;
            animation: fadeIn 0.3s ease-in-out;
        }
        
        .archive-bot-message {
            align-self: flex-start;
            background-color: #e9ecef;
            color: #333;
        }
        
        .archive-user-message {
            align-self: flex-end;
            background-color: #007bff;
            color: white;
        }
        
        .archive-chatbot-input {
            display: flex;
            padding: 10px;
            background-color: white;
            border-top: 1px solid #ddd;
        }
        
        .archive-chatbot-input input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 20px;
            margin-right: 10px;
        }
        
        .archive-chatbot-input button {
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        /* Make links in chat messages stand out */
        .archive-bot-message a {
            color: #0056b3;
            text-decoration: underline;
            font-weight: bold;
        }
        
        /* Style for project cards in responses */
        .project-search-card {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 10px;
            margin-top: 10px;
            background-color: white;
        }
        
        .project-search-card h5 {
            margin-top: 0;
            color: #0056b3;
        }
    </style>
    """
    
    chatbot_html = chatbot_styles + """
    <div class="archive-chatbot-container">
        <div class="archive-chatbot-header">
            <h4>Project Search Assistant</h4>
            <p class="text-muted">Ask me to find projects by name, category, student, or content</p>
        </div>
        <div class="archive-chatbot-messages" id="archiveChatMessages">
            <div class="archive-bot-message">
                <div class="message-content">
                    Hello! I can help you search through the project archive. Try asking me something like:
                    <ul>
                        <li>Find projects about machine learning</li>
                        <li>Show me projects by student John</li>
                        <li>Which projects use Python?</li>
                        <li>Find projects with web development tasks</li>
                    </ul>
                </div>
            </div>
        </div>
        <div class="archive-chatbot-input">
            <input type="text" id="archiveChatInput" class="form-control" placeholder="Search for projects...">
            <button id="archiveChatSendBtn" class="btn btn-primary">
                <i class="fas fa-search"></i>
            </button>
        </div>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const inputField = document.getElementById('archiveChatInput');
            const sendButton = document.getElementById('archiveChatSendBtn');
            const messagesContainer = document.getElementById('archiveChatMessages');
            
            // Function to add a message to the chat
            function addMessage(content, isUser) {
                const messageDiv = document.createElement('div');
                messageDiv.className = isUser ? 'archive-user-message' : 'archive-bot-message';
                
                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content';
                contentDiv.innerHTML = content;
                
                messageDiv.appendChild(contentDiv);
                messagesContainer.appendChild(messageDiv);
                
                // Scroll to bottom
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            
            // Function to send query to the server
            async function sendQuery(query) {
                try {
                    const response = await fetch('/student/archive/search', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ query: query }),
                    });
                    
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    
                    const data = await response.json();
                    return data.response;
                } catch (error) {
                    console.error('Error:', error);
                    return 'Sorry, I encountered an error while searching.';
                }
            }
            
            // Handle send button click
            sendButton.addEventListener('click', async function() {
                const query = inputField.value.trim();
                if (query) {
                    // Add user message
                    addMessage(query, true);
                    
                    // Clear input
                    inputField.value = '';
                    
                    // Show loading indicator
                    const loadingDiv = document.createElement('div');
                    loadingDiv.className = 'archive-bot-message';
                    loadingDiv.innerHTML = '<div class="message-content"><i>Searching projects...</i></div>';
                    messagesContainer.appendChild(loadingDiv);
                    
                    // Get response from server
                    const botResponse = await sendQuery(query);
                    
                    // Remove loading indicator
                    messagesContainer.removeChild(loadingDiv);
                    
                    // Add bot response
                    addMessage(botResponse, false);
                }
            });
            
            // Handle enter key press
            inputField.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    sendButton.click();
                }
            });
        });
    </script>
    """
    return chatbot_html

@student_routes.route('/student/projects/archive')
@login_required
@student_required
def project_archive():
    if not current_user.is_verified:
        flash_unique("Only verified students can access the project archive.", "info", persistent=False)
        return redirect(url_for('student_routes.view_projects'))

    projects = Project.query.all()
    
    # Get all projects data
    all_projects_data = []
    
    # Collect unique categories
    unique_categories = set()
    
    for project in projects:
        student = User.query.get(project.student_id)
        if student:
            # Add categories to unique set
            if project.category:
                categories = [cat.strip() for cat in project.category.split(',')]
                unique_categories.update(categories)
            
            # Only include public project information
            project_data = {
                "student_name": student.name,
                "roll_no": student.rollno,
                "project_name": project.title,
                "category": project.category,
                "summary": project.summary,
                "start_date": project.start_date.strftime('%Y-%m-%d'),
                "project_id": project.id
            }
            all_projects_data.append(project_data)
    
    # Convert the data to JSON string for use with the chatbot
    projects_json = json.dumps(all_projects_data)
    
    # Get the archive chatbot HTML
    archive_chatbot_html = get_archive_chatbot_html()
    
    return render_template('student/project_archive.html', 
                          projects=projects, 
                          projects_json=projects_json,
                          archive_chatbot_html=archive_chatbot_html)

@student_routes.route('/student/projects/view/<int:project_id>')
@login_required
@student_required
def view_archive_project(project_id):
    """View details of a specific project from the archive"""
    if not current_user.is_verified:
        flash_unique("Only verified students can view archived projects.", "info", persistent=False)
        return redirect(url_for('student_routes.view_projects'))
    
    project = Project.query.get_or_404(project_id)
    student = User.query.get(project.student_id)
    tasks = Task.query.filter_by(project_id=project_id).all()
    
    # Get task counts by status
    backlog_count = sum(1 for task in tasks if task.status == 'Backlog')
    in_progress_count = sum(1 for task in tasks if task.status == 'In Progress')
    progressed_count = sum(1 for task in tasks if task.status == 'Progressed')
    finished_count = sum(1 for task in tasks if task.status == 'Finished')
    
    return render_template('student/view_archive_project.html', 
                          project=project, 
                          student=student,
                          tasks=tasks,
                          backlog_count=backlog_count,
                          in_progress_count=in_progress_count,
                          progressed_count=progressed_count,
                          finished_count=finished_count)

# -------------------------------  Chatbot functions  ------------------------------------------

def get_memory(project_id):
    memory = memory_store.get(project_id)
    if not memory:
        memory = {'messages': []}
        memory_store[project_id] = memory

        long_memory = LongTermMemory.query.filter_by(project_id=project_id).first()
        if long_memory:
            try:
                chat_data = json.loads(long_memory.chat_content)  # Load JSON structure
                ai_msgs = chat_data.get("AI", [])
                user_msgs = chat_data.get("User", [])

                # Ensure messages are stored in sequential order
                for ai_msg, user_msg in zip(ai_msgs, user_msgs):
                    memory['messages'].append({'sender': 'User', 'content': user_msg})
                    memory['messages'].append({'sender': 'AI', 'content': ai_msg})

                # If one list is longer, add remaining messages
                if len(ai_msgs) > len(user_msgs):
                    memory['messages'].append({'sender': 'AI', 'content': ai_msgs[-1]})
                elif len(user_msgs) > len(ai_msgs):
                    memory['messages'].append({'sender': 'User', 'content': user_msgs[-1]})

            except json.JSONDecodeError:
                print(f"Error parsing chat content for project {project_id}")
        else:
            # Initialize empty memory if no previous chat exists
            new_memory = LongTermMemory(
                project_id=project_id,
                user_id=Project.query.get(project_id).student_id,
                chat_content=json.dumps({"AI": [], "User": []})  # JSON format
            )
            db.session.add(new_memory)
            db.session.commit()

    return memory


def add_message_to_buffer(memory, sender, content):
    memory['messages'].append({'sender': sender, 'content': content})
    if len(memory['messages']) > BUFFER_SIZE:
        memory['messages'].pop(0)

# ------------------  From here I will start with the tasks  -----------------------------------
def check_task_status(task):
    if task.due_date.date() < datetime.now().date():
        if task.status != 'Finished':
            task.status = 'Backlog'
            db.session.commit()
            flash_unique(f"Task '{task.title}' moved to Backlog due to overdue date.", 'warning', persistent=False)
            
@student_routes.route('/project/<int:project_id>/tasks', methods=['GET', 'POST'])
@login_required
@student_required
def view_tasks(project_id):
    project = Project.query.get_or_404(project_id)

    if current_user.id != project.student_id:
        flash("You are not authorized to view this project's tasks.", 'danger')
        return redirect(url_for('student_routes.project_archive'))

    tasks = Task.query.filter_by(project_id=project_id).all()

    for task in tasks:
        check_task_status(task)

    backlog_tasks = Task.query.filter_by(project_id=project_id, status='Backlog').all()
    in_progress_tasks = Task.query.filter_by(project_id=project_id, status='In Progress').all()
    progressed_tasks = Task.query.filter_by(project_id=project_id, status='Progressed').all()
    finished_tasks = Task.query.filter_by(project_id=project_id, status='Finished').all()

    ##########################################################################################
    # Get chat history for the project
    memory = get_memory(project_id)
    chat_history = memory['messages']

    if request.method == 'POST':
        user_message = request.form.get('message')

        if user_message and user_message.strip():
            # Add user message to memory buffer
            add_message_to_buffer(memory, 'User', render_markdown(user_message))

            # Retrieve past messages (history) for context
            previous_conversations = "\n".join(
                [f"{msg['sender']}: {msg['content']}" for msg in chat_history[-5:]]
            )

            # Create the prompt including past conversations
            prompt = f"""
            You are an AI assistant helping students with their project tasks. The project details are as follows:

            Project Summary:
            {project.summary}

            Previous Conversations:
            {previous_conversations}

            The student has asked the following question: "{user_message}"
            """

            # Get AI response based on the history and current user message
            ai_response = chat_model.invoke([HumanMessage(content=prompt)]).content or \
                          f"Here's a bit more information about the project: {project.summary}."

            # Add AI response to memory buffer
            add_message_to_buffer(memory, 'AI', render_markdown(ai_response))

            # Save updated memory to the database in JSON format
            chat_data = {"User": [], "AI": []}
            for msg in memory['messages']:
                if msg['sender'] == 'AI':
                    chat_data["AI"].append(msg['content'])
                else:
                    chat_data["User"].append(msg['content'])

            long_memory = LongTermMemory.query.filter_by(project_id=project_id).first()
            if long_memory:
                long_memory.chat_content = json.dumps(chat_data)
            else:
                long_memory = LongTermMemory(
                    project_id=project_id,
                    user_id=project.student_id,
                    chat_content=json.dumps(chat_data)
                )
                db.session.add(long_memory)
            db.session.commit()

        return jsonify({'chat_history': chat_history})

    return render_template('student/tasks.html', project=project, user=current_user,
                           backlog_tasks=backlog_tasks, in_progress_tasks=in_progress_tasks,
                           progressed_tasks=progressed_tasks, finished_tasks=finished_tasks,
                           chat_history=chat_history)
    
@student_routes.route('/student/save_chat/<project_id>', methods=['POST'])
def save_chat(project_id):
    project = Project.query.get(project_id)

    memory = get_memory(project_id)
    chat_history = memory['messages']

    if chat_history:
        chat_data = {"AI": [], "User": []}
        for msg in chat_history:
            if msg['sender'] == 'AI':
                chat_data["AI"].append(msg['content'])
            else:
                chat_data["User"].append(msg['content'])

        # Update LongTermMemory with JSON
        long_memory = LongTermMemory.query.filter_by(project_id=project_id).first()
        if long_memory:
            long_memory.chat_content = json.dumps(chat_data)
        else:
            long_memory = LongTermMemory(
                project_id=project_id,
                user_id=project.student_id,
                chat_content=json.dumps(chat_data)
            )
            db.session.add(long_memory)
        db.session.commit()

        memory_store[project_id]['messages'] = []

    return redirect(url_for('student_routes.view_tasks', project_id=project.id))


@student_routes.route('/project/<int:project_id>/tasks/add', methods=['GET', 'POST'])
@login_required
@student_required
def add_task(project_id):
    project = Project.query.get_or_404(project_id)

    if current_user.id != project.student_id:
        flash("You are not authorized to add tasks to this project.", 'danger')
        return redirect(url_for('student_routes.project_archive'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        due_date = datetime.strptime(request.form['due_date'], '%Y-%m-%d')

        new_task = Task(title=title, description=description, due_date=due_date, status='In Progress', project_id=project_id)
        db.session.add(new_task)
        db.session.commit()

        flash_unique('New task added successfully!', 'success', persistent=False)
        return redirect(url_for('student_routes.view_tasks', project_id=project_id))

    return render_template('student/add_task.html', project=project)

@student_routes.route('/task/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
@student_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    project_id = task.project_id
    project = Project.query.get_or_404(project_id)

    if current_user.id != project.student_id:
        flash("You are not authorized to edit tasks in this project.", 'danger')
        return redirect(url_for('student_routes.project_archive'))

    if request.method == 'POST':
        task.title = request.form['title']
        task.description = request.form['description']
        task.due_date = datetime.strptime(request.form['due_date'], '%Y-%m-%d')
        
        # Check if the due date has passed
        if task.due_date.date() < datetime.now().date():
            if task.status != 'Backlog':
                task.status = 'Backlog'
                flash_unique(f"Task '{task.title}' moved to Backlog due to overdue date.", 'warning')

        db.session.commit()
        flash_unique('Task updated successfully!', 'success', persistent=False)
        return redirect(url_for('student_routes.view_tasks', project_id=project_id))

    return render_template('student/edit_task.html', task=task)

@student_routes.route('/task/<int:task_id>/change_status', methods=['POST'])
@login_required
@student_required
def change_task_status(task_id):
    task = Task.query.get_or_404(task_id)
    project_id = task.project_id
    project = Project.query.get_or_404(project_id)

    if current_user.id != project.student_id:
        flash("You are not authorized to change tasks in this project.", 'info')
        return redirect(url_for('student_routes.project_archive'))

    new_status = request.form['status']
    task.status = new_status
    db.session.commit()

    flash_unique(f"Task status updated to '{new_status}'", 'success', persistent=False)
    return redirect(url_for('student_routes.view_tasks', project_id=project_id))


@student_routes.route('/task/<int:task_id>/delete', methods=['POST'])
@login_required
@student_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    project_id = task.project_id
    project = Project.query.get_or_404(project_id)

    if current_user.id != project.student_id:
        flash("You are not authorized to delete tasks in this project.", 'danger')
        return redirect(url_for('student_routes.project_archive'))

    db.session.delete(task)
    db.session.commit()
    flash_unique('Task deleted successfully!', 'success', persistent=False)
    return redirect(url_for('student_routes.view_tasks', project_id=project_id))

# ------------------  Assigned Project Working  -----------------------------------
@student_routes.route('/assigned-projects')
@login_required
@student_required
def assigned_projects():
    projects = db.session.query(MiniAdminProject, db.func.count(MiniAdminProjectStudent.student_id).label('student_count'))\
    .join(MiniAdminProjectStudent, MiniAdminProject.id == MiniAdminProjectStudent.project_id)\
    .filter(MiniAdminProjectStudent.student_id == current_user.id)\
    .group_by(MiniAdminProject.id).all()
    
    return render_template('student/assigned_projects.html', projects=projects)
    
@student_routes.route('/assigned-projects/<int:project_id>/tasks')
@login_required
@student_required
def view_assigned_tasks(project_id):
    project = MiniAdminProject.query.get_or_404(project_id)

    if not MiniAdminProjectStudent.query.filter_by(student_id=current_user.id, project_id=project_id).first():
        flash("You are not authorized to view this project's tasks.", 'danger')
        return redirect(url_for('student_routes.assigned_projects'))

    tasks = MiniAdminProjectTask.query.filter_by(miniadmin_project_id=project_id).all()

    for task in tasks:
        check_task_status(task)

    backlog_tasks = MiniAdminProjectTask.query.filter_by(miniadmin_project_id=project_id, status='Backlog').all()
    in_progress_tasks = MiniAdminProjectTask.query.filter_by(miniadmin_project_id=project_id, status='In Progress').all()
    progressed_tasks = MiniAdminProjectTask.query.filter_by(miniadmin_project_id=project_id, status='Progressed').all()
    finished_tasks = MiniAdminProjectTask.query.filter_by(miniadmin_project_id=project_id, status='Finished').all()

    return render_template('student/assigned_tasks.html', project=project, user=current_user,
                           backlog_tasks=backlog_tasks, in_progress_tasks=in_progress_tasks,
                           progressed_tasks=progressed_tasks, finished_tasks=finished_tasks)

@student_routes.route('/assigned-projects/task/<int:task_id>/change_status', methods=['POST'])
@login_required
@student_required
def change_assigned_task_status(task_id):
    task = MiniAdminProjectTask.query.get_or_404(task_id)
    project_id = task.miniadmin_project_id
    project = MiniAdminProject.query.get_or_404(project_id)

    assigned_project = MiniAdminProjectStudent.query.filter_by(student_id=current_user.id, project_id=project.id).first()
    
    if not assigned_project:
        flash("You are not authorized to change tasks in this project.", 'info')
        return redirect(url_for('student_routes.assigned_projects'))

    new_status = request.form['status']
    task.status = new_status
    db.session.commit()

    flash_unique(f"Task status updated to '{new_status}'", 'success', persistent=False)
    return redirect(url_for('student_routes.view_assigned_tasks', project_id=project_id))

@student_routes.route('/student/profile', methods=['GET', 'POST'])
@login_required
@student_required
def student_profile():
    if request.method == 'POST':
        name = request.form.get('name')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if name:
            current_user.name = name
        
        if new_password:
            if new_password != confirm_password:
                flash_unique('Passwords do not match!', 'danger', persistent=False)
                return redirect(url_for('student_routes.student_profile'))
            
            if len(new_password) < 6:
                flash_unique('Password must be at least 6 characters long!', 'danger', persistent=False)
                return redirect(url_for('student_routes.student_profile'))
                
            # Hash the new password before saving
            hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
            current_user.password = hashed_password
        
        db.session.commit()
        flash_unique('Profile updated successfully!', 'success', persistent=False)
        return redirect(url_for('student_routes.student_profile'))

    return render_template('student/profile.html', user=current_user)

@student_routes.route('/api/projects/data', methods=['GET'])
@login_required
@student_required
def get_projects_data():
    """API endpoint that returns all projects data as JSON for the chatbot to use"""
    if not current_user.is_verified:
        return jsonify({"error": "Only verified students can access project data"}), 403
    
    projects = Project.query.all()
    
    all_projects_data = []
    for project in projects:
        student = User.query.get(project.student_id)
        
        if student:
            # Get all tasks for this project
            tasks = Task.query.filter_by(project_id=project.id).all()
            task_data = []
            
            for task in tasks:
                task_info = {
                    "title": task.title,
                    "description": task.description,
                    "status": task.status,
                    "due_date": task.due_date.strftime('%Y-%m-%d')
                }
                task_data.append(task_info)
            
            # Comprehensive project data including tasks
            project_data = {
                "student_name": student.name,
                "roll_no": student.rollno,
                "project_name": project.title,
                "category": project.category,
                "summary": project.summary,
                "start_date": project.start_date.strftime('%Y-%m-%d'),
                "project_id": project.id,
                "tasks": task_data
            }
            all_projects_data.append(project_data)
    
    return jsonify(all_projects_data)

def get_archive_memory():
    """Get or create memory for archive chatbot"""
    if 'archive' not in archive_memory_store:
        archive_memory_store['archive'] = {'messages': []}
    return archive_memory_store['archive']

def add_message_to_archive_buffer(memory, sender, content):
    """Add message to archive memory buffer"""
    memory['messages'].append({'sender': sender, 'content': content})
    if len(memory['messages']) > BUFFER_SIZE:
        memory['messages'].pop(0)

@student_routes.route('/student/archive/search', methods=['POST'])
@login_required
@student_required
def archive_search_chatbot():
    """Handles search queries from the archive chatbot"""
    if not current_user.is_verified:
        return jsonify({"error": "Only verified students can use this feature"}), 403
    
    user_query = request.json.get('query', '')
    
    if not user_query.strip():
        return jsonify({"response": "Please enter a search query."})
    
    # Get memory for this conversation
    memory = get_archive_memory()
    
    # Add user message to memory
    add_message_to_archive_buffer(memory, 'User', user_query)
    
    # Get conversation history
    conversation_history = "\n".join(
        [f"{msg['sender']}: {msg['content']}" for msg in memory['messages'][-5:]]
    )
    
    # Get all projects data
    projects = Project.query.all()
    all_projects_data = []
    
    # Collect unique categories
    unique_categories = set()
    
    for project in projects:
        student = User.query.get(project.student_id)
        if student:
            # Add categories to unique set
            if project.category:
                categories = [cat.strip() for cat in project.category.split(',')]
                unique_categories.update(categories)
            
            # Only include public project information
            project_data = {
                "student_name": student.name,
                "roll_no": student.rollno,
                "project_name": project.title,
                "category": project.category,
                "summary": project.summary,
                "start_date": project.start_date.strftime('%Y-%m-%d'),
                "project_id": project.id
            }
            all_projects_data.append(project_data)
    
    # Prepare system message for better context
    system_message = """You are an advanced AI project search assistant powered by Google's Gemini model.
    Your capabilities include:
    1. Natural language understanding and processing
    2. Semantic search and matching
    3. Context-aware responses
    4. Intelligent project categorization
    5. Detailed project analysis
    6. Conversational memory and context retention
    7. Adaptive response formatting
    8. Smart project grouping and recommendations
    9. Date-based analysis
    10. Category-based insights
    
    Your responses should be:
    - Precise and accurate
    - Well-structured and formatted
    - Contextually relevant
    - Informative but concise
    - Easy to read and understand
    """
    
    # Prepare prompt for search
    prompt = f"""
    {system_message}
    
    Previous conversation:
    {conversation_history}
    
    The user query is: "{user_query}"
    
    Available Categories: {', '.join(sorted(unique_categories))}
    Project Data: {json.dumps(all_projects_data)}
    
    Instructions for response:
    1. First, analyze the user's query to understand their intent and requirements
    2. Search through the project data to find relevant matches
    3. Format your response in a clear, structured way using markdown
    4. If no projects match exactly, suggest related categories or topics
    5. For matching projects, provide a concise overview focusing on key points
    
    Response Format:
    If projects are found:
    ```
    Here are the projects matching your query:

    **Project Title** by Student Name
    Categories: **Category1**, **Category2**
    Start Date: YYYY-MM-DD

    Key Points:
    * Point 1
    * Point 2
    * Point 3
    ```

    If no projects match:
    ```
    No projects found matching your query. Here are the available categories:
    * **Category1**
    * **Category2**
    ...
    ```

    Guidelines:
    1. Use proper markdown formatting
    2. Keep responses concise and focused on key points
    3. Use bullet points for better readability
    4. Highlight important information in bold
    5. Limit to 3-4 key points per project
    6. Focus on the most relevant aspects of the project
    7. Avoid lengthy descriptions
    8. Use clear, direct language
    9. Maintain consistent formatting
    10. Prioritize the most important information
    """
    
    # Get chat response using Gemini's advanced features
    messages = [
        HumanMessage(content=prompt)
    ]
    
    response = chat_model.invoke(messages).content
    
    # Render markdown in the response
    rendered_response = render_markdown(response)
    
    # Add bot response to memory
    add_message_to_archive_buffer(memory, 'AI', rendered_response)
    
    return jsonify({"response": rendered_response})
