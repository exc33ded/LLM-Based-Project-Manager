from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
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

chat_model = ChatGoogleGenerativeAI(model="gemini-2.0-flash-thinking-exp-01-21")

memory_store = {}

def render_markdown(content):
    return markdown.markdown(content)

# Buffer memory configuration (keeps the last N messages)
BUFFER_SIZE = 20

def check_student_role(current_user):
    if current_user.role != 'student':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    return None

@student_routes.route('/student/dashboard', methods=['GET', 'POST'])
@login_required
def student_dashboard():
    result = check_student_role(current_user)
    if result:
        return result
    
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
def view_projects():
    result = check_student_role(current_user)
    if result:
        return result
    
    user = User.query.get_or_404(current_user.id)
    projects = Project.query.filter_by(student_id=current_user.id).all()
    return render_template('student/view_projects.html', projects=projects, user=user)

@student_routes.route('/student/projects/add', methods=['GET', 'POST'])
@login_required
def add_project():
    result = check_student_role(current_user)
    if result:
        return result

    if request.method == 'POST':
        title = request.form['title']
        start_date_str = request.form['start_date']
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') 
        synopsis = request.files['synopsis']

        # Generate a unique filename for the uploaded synopsis
        num = random.randint(1, 10000)
        unique_synopsis_filename = f"{current_user.name}_{current_user.rollno}__{num}__{title}_synopsis.{synopsis.filename.split('.')[-1]}"
        synopsis_filename = secure_filename(unique_synopsis_filename)
        synopsis_path = os.path.join(UPLOAD_FOLDER, synopsis_filename)
        synopsis.save(synopsis_path)

        # Analyze the synopsis using the AI script
        ai_result = analyze_synopsis(synopsis_path)

        # Handle errors during AI analysis
        if "error" in ai_result:
            flash(ai_result["error"], "danger")
            return redirect(url_for('student_routes.add_project'))

        # Parse AI analysis result
        ai_data = json.loads(ai_result)
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
def edit_project(project_id):
    result = check_student_role(current_user)
    if result:
        return result

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
def delete_project(project_id):
    result = check_student_role(current_user)
    if result:
        return result

    project = Project.query.get_or_404(project_id)

    if project.student_id != current_user.id:
        flash('Unauthorized to delete this project', 'danger')
        return redirect(url_for('student_routes.view_projects'))

    try:
        LongTermMemory.query.filter_by(project_id=project_id).delete()

        db.session.delete(project)
        db.session.commit()
        memory_store.pop(project_id, None)

        flash_unique("Project and its chat history deleted successfully!", "success", persistent=False)

    except Exception as e:
        db.session.rollback()  
        flash_unique(f"Error deleting project: {str(e)}", "danger", persistent=False)

    return redirect(url_for('student_routes.view_projects'))


@student_routes.route('/student/projects/archive')
@login_required
def project_archive():
    result = check_student_role(current_user)
    if result:
        return result
    
    if not current_user.is_verified:
        flash_unique("Only verified students can access the project archive.", "info", persistent=False)
        return redirect(url_for('student_routes.view_projects'))

    projects = Project.query.all()
    return render_template('student/project_archive.html', projects=projects)

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
                          f"Here’s a bit more information about the project: {project.summary}."

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
def assigned_projects():
    result = check_student_role(current_user)
    if result:
        return result
    
    projects = db.session.query(MiniAdminProject, db.func.count(MiniAdminProjectStudent.student_id).label('student_count'))\
    .join(MiniAdminProjectStudent, MiniAdminProject.id == MiniAdminProjectStudent.project_id)\
    .filter(MiniAdminProjectStudent.student_id == current_user.id)\
    .group_by(MiniAdminProject.id).all()
    
    return render_template('student/assigned_projects.html', projects=projects)
    
@student_routes.route('/assigned-projects/<int:project_id>/tasks')
@login_required
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
