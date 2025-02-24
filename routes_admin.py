from flask import Blueprint, render_template, redirect, url_for, flash, request
from models import User, Project, Task, MiniAdminProject, MiniAdminProjectTask, MiniAdminProjectStudent
from extensions import db
from flask_login import login_user, login_required, current_user, logout_user
from werkzeug.security import check_password_hash
from datetime import datetime
import random
from utils.pdf_summarize import analyze_synopsis
from utils.task_generation import generate_dynamic_coding_tasks
from utils.no_again_flash import flash_unique
from werkzeug.utils import secure_filename
import os
import json

UPLOAD_FOLDER = 'static/uploads/synopsis'

admin_routes = Blueprint('admin_routes', __name__)

@admin_routes.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email, role='admin').first()  # Check for admin role
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash_unique('Admin login successful!', 'success')
            return redirect(url_for('admin_routes.admin_dashboard'))
        else:
            flash_unique('Invalid email or password', 'danger')
    return render_template('admin_login.html')


@admin_routes.route('/admin/dashboard', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    # Fetch general statistics
    assigned_students_count = User.query.filter(User.miniadmin_id != None).count()
    unassigned_students_count = User.query.filter(User.miniadmin_id == None, User.role == 'student').count()
    unverified_students_count = User.query.filter_by(role='student', is_verified=False).count()
    unverified_instructors_count = User.query.filter_by(role='instructor', is_verified=False).count()

    # Count of tasks by status
    backlog_tasks_count = Task.query.filter_by(status='Backlog').count()
    in_progress_tasks_count = Task.query.filter_by(status='In Progress').count()
    progressed_tasks_count = Task.query.filter_by(status='Progressed').count()  # Added Progressed Tasks
    completed_tasks_count = Task.query.filter_by(status='Finished').count()

    # Fetch a list of all projects for task categorization
    projects = Project.query.all()

    # If the admin selects a project, get the task count for that project
    selected_project = None
    project_backlog = 0
    project_in_progress = 0
    project_progressed = 0
    project_finished = 0

    if request.method == 'POST':
        project_id = request.form.get('project_id')
        if project_id:
            selected_project = Project.query.get_or_404(project_id)
            tasks = Task.query.filter_by(project_id=project_id).all()
            for task in tasks:
                if task.status == 'Backlog':
                    project_backlog += 1
                elif task.status == 'In Progress':
                    project_in_progress += 1
                elif task.status == 'Progressed':
                    project_progressed += 1
                elif task.status == 'Finished':
                    project_finished += 1

    return render_template(
        'admin/admin_dashboard.html',
        assigned_students_count=assigned_students_count,
        unassigned_students_count=unassigned_students_count,
        unverified_students_count=unverified_students_count,
        unverified_instructors_count=unverified_instructors_count,
        backlog_tasks_count=backlog_tasks_count,
        in_progress_tasks_count=in_progress_tasks_count,
        progressed_tasks_count=progressed_tasks_count,  
        completed_tasks_count=completed_tasks_count,
        projects=projects,
        selected_project=selected_project,
        project_backlog=project_backlog,
        project_in_progress=project_in_progress,
        project_progressed=project_progressed,
        project_finished=project_finished
    )

@admin_routes.route('/admin/assignments')
@login_required
def admin_assignment_overview():
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    mini_admins = User.query.filter_by(role='mini-admin').all()
    
    return render_template('admin/admin_assignments.html', mini_admins=mini_admins)

@admin_routes.route('/admin/verify_users')
@login_required
def verify_users():
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    pending_users = User.query.filter_by(is_verified=False).all()
    return render_template('admin/verify_users.html', pending_users=pending_users)

@admin_routes.route('/admin/verify_users/<int:user_id>', methods=['GET', 'POST'])
@login_required
def verify_user(user_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        admin_comments = request.form.get('admin_comments')
        verification_status = request.form.get('verification_status')

        user.admin_comments = admin_comments

        if verification_status == 'verify':
            user.is_verified = True
            flash_unique(f"User {user.name} has been verified.", 'success')
        elif verification_status == 'not_verify':
            user.is_verified = False
            flash_unique(f"User {user.name} has not been verified.", 'danger')

        db.session.commit() 

        return redirect(url_for('admin_routes.verify_users'))

    return render_template('admin/verify_user.html', user=user)

@admin_routes.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash_unique(f"User {user.name} has been deleted.", 'success')
    else:
        flash_unique('User not found.', 'danger')
    return redirect(url_for('admin_routes.verify_users'))

@admin_routes.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash_unique('You have been logged out.', 'info')
    return redirect(url_for('admin_routes.admin_login'))

# ------------------------------ Managing Project with Tasks for the students ----------------------------------

@admin_routes.route('/admin/projects/create/<int:user_id>', methods=['GET', 'POST'])
@login_required
def add_project(user_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    user = User.query.get_or_404(user_id)
    
    title_name = ""
    if request.method == 'POST':
        title = request.form['title']
        title_name = title
        start_date_str = request.form['start_date']
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') 
        synopsis = request.files['synopsis']
        num = random.randint(1, 10000)
        
        unique_synopsis_filename = f"{current_user.name}_{current_user.rollno}__{num}__{title}_synopsis.{synopsis.filename.split('.')[-1]}"
        synopsis_filename = secure_filename(unique_synopsis_filename)
        synopsis.save(os.path.join(UPLOAD_FOLDER, synopsis_filename))

        # Analyze the synopsis using AI
        ai_result = analyze_synopsis(os.path.join(UPLOAD_FOLDER, synopsis_filename))

        # Handle errors during AI analysis
        if "error" in ai_result:
            flash_unique(ai_result["error"], "danger")
            return redirect(url_for('admin_routes.add_project', user_id=user.id))

        # Parse AI analysis result
        ai_data = json.loads(ai_result)
        summary = ai_data.get("summary", "No summary provided.")
        categories = ai_data.get("categories", ["Other"])
        category = ", ".join(categories)

        # Create and save the project
        new_project = Project(
            title=title, 
            start_date=start_date, 
            synopsis_filename=synopsis_filename, 
            student_id=user.id, 
            summary=summary,
            category=category
        )
        db.session.add(new_project)
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
                    project_id=new_project.id
                )
                db.session.add(new_task)
            db.session.commit()
        except ValueError or Exception as e:
            flash_unique(f"Task generation failed: {e}", "danger")
            return redirect(url_for('admin_routes.view_student_projects', user_id=user.id))

        flash_unique(f"Project {title_name} added successfully!", "success")
        return redirect(url_for('admin_routes.view_student_projects', user_id=user.id))

    return render_template('admin/create_project.html', user=user)

@admin_routes.route('/admin/projects/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    project = Project.query.get_or_404(project_id)

    if not project:
        flash_unique('Project not found', 'danger')
        return redirect(url_for('admin_routes.view_projects'))

    category_colors = ['#FFCDD2', '#F8BBD0', '#E1BEE7', '#D1C4E9', '#C5CAE9', '#BBDEFB', '#B3E5FC', '#B2EBF2', '#B2DFDB', '#C8E6C9', '#DCEDC8', '#F0F4C3']

    if request.method == 'POST':
        title = request.form['title']
        start_date_str = request.form['start_date']

        start_date = project.start_date
        
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')

        synopsis = request.files.get('synopsis')

        # Update title and start date
        project.title = title
        project.start_date = start_date

        # Get the updated categories from the hidden input
        updated_categories = request.form.get('categories', '')
        project.category = updated_categories

        # If a new synopsis is uploaded
        if synopsis:
            unique_synopsis_filename = secure_filename(f"{project.id}_{title}_synopsis.{synopsis.filename.split('.')[-1]}")
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
                flash_unique("AI analysis failed: " + analysis_result['error'], "warning")

        db.session.commit()
        flash_unique("Project updated successfully!", "success", persistent=False)
        return redirect(url_for('admin_routes.view_projects'))

    return render_template('admin/edit_project.html', project=project, category_colors=category_colors)


def check_task_status(task):
    if task.due_date.date() < datetime.now().date():
        if task.status != 'Finished':
            task.status = 'Backlog'
            db.session.commit()
            flash_unique(f"Task '{task.title}' moved to Backlog due to overdue date.", 'warning')

@admin_routes.route('/admin/projects')
@login_required
def view_projects():
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    users = User.query.all()
    student_projects = [(user, len(user.projects)) for user in users if user.role == 'student']
    
    return render_template('admin/view_projects.html', student_projects=student_projects)

@admin_routes.route('/admin/projects/<int:user_id>')
@login_required
def view_student_projects(user_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    user = User.query.get_or_404(user_id)
    projects = Project.query.filter_by(student_id=user.id).all()
    
    return render_template('admin/view_student_projects.html', user=user, projects=projects)

@admin_routes.route('/admin/projects/<int:project_id>/tasks', methods=['GET'])
@login_required
def view_project_tasks(project_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    user_id = request.args.get('user_id')
    user = User.query.get_or_404(user_id) if user_id else None
    
    project = Project.query.get_or_404(project_id)
    tasks = Task.query.filter_by(project_id=project.id).all()

    for task in tasks:
        check_task_status(task)
    
    # Categorize tasks by status
    backlog_tasks = [task for task in tasks if task.status == 'Backlog']
    in_progress_tasks = [task for task in tasks if task.status == 'In Progress']
    progressed_tasks = [task for task in tasks if task.status == 'Progressed']
    finished_tasks = [task for task in tasks if task.status == 'Finished']

    return render_template('admin/view_project_tasks.html', user=user, project=project, 
                           backlog_tasks=backlog_tasks, 
                           in_progress_tasks=in_progress_tasks, 
                           progressed_tasks=progressed_tasks, 
                           finished_tasks=finished_tasks)

@admin_routes.route('/admin/projects/tasks/move/<int:task_id>', methods=['POST'])
@login_required
def move_task(task_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    task = Task.query.get_or_404(task_id)
    new_status = request.form.get('status')  # Get the new status from the form
    task.status = new_status

    db.session.commit()
    flash_unique(f'Task moved to {new_status} successfully!', 'success', persistent=False)
    return redirect(url_for('admin_routes.view_project_tasks', project_id=task.project_id))

@admin_routes.route('/admin/projects/tasks/add/<int:project_id>', methods=['GET', 'POST'])
@login_required
def add_task(project_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    project = Project.query.get_or_404(project_id) 

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        due_date_str = request.form['due_date']
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()

        default_status = 'Backlog' 
        new_task = Task(title=title, description=description, due_date=due_date, status=default_status, project_id=project_id)
        
        db.session.add(new_task)
        db.session.commit()
        flash_unique('Task added successfully!', 'success', persistent=False)
        return redirect(url_for('admin_routes.view_project_tasks', project_id=project_id))

    return render_template('admin/add_task.html', project=project)


@admin_routes.route('/admin/projects/tasks/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    task = Task.query.get_or_404(task_id)

    if request.method == 'POST':
        task.title = request.form['title']
        task.description = request.form['description']
   
        due_date_str = request.form['due_date']
        task.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() 

        db.session.commit()
        flash_unique('Task updated successfully!', 'success', persistent=False)
        return redirect(url_for('admin_routes.view_project_tasks', project_id=task.project_id))

    return render_template('admin/edit_task.html', task=task)

@admin_routes.route('/admin/projects/tasks/delete/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()

    flash_unique('Task deleted successfully!', 'success', persistent=False)
    return redirect(url_for('admin_routes.view_project_tasks', project_id=task.project_id))

@admin_routes.route('/admin/projects/delete/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash_unique(f"Project '{project.title}' has been deleted.", 'success', persistent=False)
    return redirect(url_for('admin_routes.view_projects'))


# ------------------------ Mini-Admin Work --------------------------------------------

@admin_routes.route('/admin/assign_students', methods=['GET', 'POST'])
@login_required
def assign_students():
    if current_user.role != 'admin':
        flash_unique('Access denied.', 'danger')
        return redirect(url_for('auth_routes.login'))

    # Fetch mini-admins and unassigned students
    mini_admins = User.query.filter_by(role='mini-admin', is_verified=True).all()
    students = User.query.filter_by(role='student', miniadmin_id=None, is_verified=True).all()

    if request.method == 'POST':
        selected_miniadmin = request.form.get('miniadmin_id')

        if not selected_miniadmin:
            flash_unique('Mini-admin selection is required!', 'danger')
            return redirect(url_for('admin_routes.assign_students'))

        selected_students = request.form.getlist('students')

        miniadmin = User.query.get(selected_miniadmin)
        for student_id in selected_students:
            student = User.query.get(student_id)
            student.miniadmin_id = miniadmin.id
            db.session.commit()

        flash_unique('Students assigned successfully!', 'success', persistent=False)

        return redirect(url_for('admin_routes.assign_students'))

    return render_template('admin/assign_students.html', mini_admins=mini_admins, students=students)



@admin_routes.route('/admin/unassign_student', methods=['POST'])
@login_required
def unassign_student():
    if current_user.role != 'admin':
        flash_unique('Access denied.', 'danger')
        return redirect(url_for('auth_routes.login'))

    student_id = request.form.get('student_id')
    miniadmin_id = request.form.get('miniadmin_id')

    # Fetch the student and mini-admin
    student = User.query.get(student_id)
    miniadmin = User.query.get(miniadmin_id)

    if student:
        if miniadmin:  # Ensure miniadmin is found
            # Unassign the student from the mini-admin
            miniadmin.assigned_students.remove(student)
            student.miniadmin_id = None
            db.session.commit()
            flash_unique(f'Student {student.name} has been unassigned successfully!', 'success', persistent=False)
        else:
            flash_unique('Mini-admin not found!', 'danger')
    else:
        flash_unique('Student not found!', 'danger')

    return redirect(url_for('admin_routes.admin_dashboard'))  # Redirect to the admin dashboard after unassignment


@admin_routes.route('/admin/unassign_all', methods=['POST'])
@login_required
def unassign_all():
    if current_user.role != 'admin':
        flash_unique('Access denied.', 'danger')
        return redirect(url_for('auth_routes.login'))

    miniadmin_id = request.form.get('miniadmin_id')

    if miniadmin_id:
        miniadmin = User.query.get(miniadmin_id)
        
        if miniadmin:
            students = User.query.filter_by(miniadmin_id=miniadmin_id).all()
            
            for student in students:
                student.miniadmin_id = None
                if student in miniadmin.assigned_students:
                    miniadmin.assigned_students.remove(student)

            db.session.commit()
            flash_unique('All students unassigned successfully!', 'success', persistent=False)
        else:
            flash_unique('Mini-admin not found!', 'danger')
    else:
        flash_unique('Invalid request!', 'danger')

    return redirect(url_for('admin_routes.admin_dashboard')) 

# ----------------------------- Admin Mentor Project Managment --------------------------------
@admin_routes.route('/admin/mentor/project', methods=['GET'])
@login_required
def mentor_project():
    if current_user.role != 'admin':
        flash_unique('Access denied.', 'danger')
        return redirect(url_for('auth_routes.login'))

    mini_admins = User.query.filter_by(role='mini-admin').all()
    
    mini_admin_data = []

    for mini_admin in mini_admins:
        projects = MiniAdminProject.query.filter_by(miniadmin_id=mini_admin.id).all()

        students = User.query.filter_by(miniadmin_id=mini_admin.id).all()
        
        mini_admin_data.append({
            'mini_admin': mini_admin,
            'projects': projects,
            'students': students
        })

    return render_template('admin/view_miniadmin_projects.html', mini_admin_data=mini_admin_data)

@admin_routes.route('/admin/mentor/project/<int:miniadmin_id>', methods=['GET'])
@login_required
def view_mentor_projects(miniadmin_id):
    if current_user.role != 'admin':
        flash_unique('Access denied.', 'danger')
        return redirect(url_for('auth_routes.login'))

    mini_admin = User.query.get_or_404(miniadmin_id)

    projects = MiniAdminProject.query.filter_by(miniadmin_id=mini_admin.id).all()

    project_data = []
    
    for project in projects:
        assigned_students = [assignment.student for assignment in project.assigned_students]  
        project_data.append({
            'project': project,
            'students': assigned_students
        })

    return render_template('admin/view_miniadmin_details.html', mini_admin=mini_admin, project_data=project_data)

@admin_routes.route('/admin/mentor/projects/<int:project_id>/tasks', methods=['GET'])
@login_required
def view_miniadmin_project_tasks(project_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    project = MiniAdminProject.query.get_or_404(project_id)

    mini_admin = User.query.get_or_404(project.miniadmin_id)

    tasks = MiniAdminProjectTask.query.filter_by(miniadmin_project_id=project.id).all()

    for task in tasks:
        check_task_status(task)

    backlog_tasks = [task for task in tasks if task.status == 'Backlog']
    in_progress_tasks = [task for task in tasks if task.status == 'In Progress']
    progressed_tasks = [task for task in tasks if task.status == 'Progressed']
    finished_tasks = [task for task in tasks if task.status == 'Finished']

    return render_template('admin/view_project_miniadmin_tasks.html', 
                           mini_admin=mini_admin, 
                           project=project, 
                           backlog_tasks=backlog_tasks, 
                           in_progress_tasks=in_progress_tasks, 
                           progressed_tasks=progressed_tasks, 
                           finished_tasks=finished_tasks,
                           back_url=url_for('admin_routes.view_mentor_projects', miniadmin_id=mini_admin.id))

@admin_routes.route('/admin/mentor/projects/<int:project_id>/add_task', methods=['GET', 'POST'])
@login_required
def add_miniadmin_task(project_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    
    project = MiniAdminProject.query.get_or_404(project_id) 

    if request.method == 'POST':
        default_status = 'In Progress'

        title = request.form['title']
        description = request.form['description']
        due_date_str = request.form['due_date']
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        status = default_status  

        new_task = MiniAdminProjectTask(
            title=title,
            description=description,
            due_date=due_date,
            status=status,
            miniadmin_project_id=project_id
        )
        db.session.add(new_task)
        db.session.commit()
        flash_unique("Task Added Successfully!", "success", persistent=False)
        return redirect(url_for('admin_routes.view_miniadmin_project_tasks', project_id=project_id))
    return render_template('admin/add_miniadmin_task.html', project=project)

@admin_routes.route('/admin/mentor/projects/delete_task/<int:task_id>', methods=['GET', 'POST'])
@login_required
def delete_miniadmin_task(task_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    task = MiniAdminProjectTask.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    flash_unique('Task deleted successfully!', 'success', persistent=False)
    return redirect(url_for('admin_routes.view_miniadmin_project_tasks', project_id=task.miniadmin_project_id))

@admin_routes.route('/admin/mentor/projects/tasks/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_miniadmin_task(task_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    task = MiniAdminProjectTask.query.get_or_404(task_id)

    if request.method == 'POST':
        new_title = request.form.get('title', '').strip()
        new_description = request.form.get('description', '').strip()
        new_due_date = request.form.get('due_date', '').strip()
        new_status = request.form.get('status', '').strip()

        if new_title:
            task.title = new_title
        if new_description:
            task.description = new_description
        if new_due_date:
            try:
                task.due_date = datetime.strptime(new_due_date, '%Y-%m-%d')
            except ValueError:
                flash("Invalid date format. Please use YYYY-MM-DD.", "error")
                return redirect(url_for('edit_task', task_id=task.id))
        if new_status:
            task.status = new_status

        db.session.commit()
        flash_unique('Task updated successfully!', 'success', persistent=False)
        return redirect(url_for('admin_routes.view_miniadmin_project_tasks', project_id=task.miniadmin_project_id))

    return render_template('admin/edit_miniadmin_task.html', task=task)

@admin_routes.route('/admin/mentor/projects/move_task/<int:task_id>', methods=['POST'])
@login_required
def move_miniadmin_task(task_id):
    if current_user.role != 'admin':
        flash_unique('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    new_status = request.form.get('status')
    task = MiniAdminProjectTask.query.get_or_404(task_id)

    if task.due_date < datetime.utcnow():
        flash_unique("Task is overdue! Please update the due date before moving.", "warning", persistent=False)
        return redirect(url_for('admin_routes.view_miniadmin_project_tasks', project_id=task.miniadmin_project_id))

    task.status = new_status
    db.session.commit()
    
    flash_unique(f'Task moved to {new_status} successfully!', 'success', persistent=False)
    return redirect(url_for('admin_routes.view_miniadmin_project_tasks', project_id=task.miniadmin_project_id))

@admin_routes.route('/admin/mentor/project/<int:miniadmin_id>/create', methods=['GET', 'POST'])
@login_required
def update_miniadmin_project_create(miniadmin_id):
    if current_user.role != 'admin':
        flash_unique('Access denied.', 'danger')
        return redirect(url_for('auth_routes.login'))

    mini_admin = User.query.get_or_404(miniadmin_id)
    assigned_students = User.query.filter_by(miniadmin_id=miniadmin_id).all()

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        selected_student_ids = request.form.getlist('students') 
        generate_ai_tasks = request.form.get("generate_ai_tasks") == "on"

        print(f"🔍 Selected Students: {selected_student_ids}")  

        if not title or not description:
            flash_unique('Title and Description are required.', 'danger')
            return redirect(request.url)

        new_project = MiniAdminProject(title=title, description=description, miniadmin_id=miniadmin_id)
        db.session.add(new_project)
        db.session.commit()

        if selected_student_ids:
            for student_id in selected_student_ids:
                student_assignment = MiniAdminProjectStudent(
                    project_id=new_project.id,
                    student_id=int(student_id)
                )
                db.session.add(student_assignment)

            db.session.commit() 

            print(f"✅ Students assigned to project {new_project.id}: {selected_student_ids}")

        if generate_ai_tasks:
            try:
                task_data = json.loads(generate_dynamic_coding_tasks(description))
                for task_title, task_details in task_data.items():
                    new_task = MiniAdminProjectTask(
                        title=task_title,
                        description=task_details["Task Description"],
                        due_date=datetime.strptime(task_details["Date"], '%Y-%m-%d'),
                        status="In Progress",
                        miniadmin_project_id=new_project.id
                    )
                    db.session.add(new_task)

                db.session.commit()  
                flash_unique("Project and AI-generated tasks created successfully!", "success", persistent=False)

            except Exception as e:
                flash_unique(f"AI Task generation failed: {e}", "danger")

        else:
            flash_unique("Project created successfully!", "success", persistent=False)

        return redirect(url_for('admin_routes.view_mentor_projects', miniadmin_id=miniadmin_id))

    return render_template(
        'admin/create_project_miniadmin.html',
        mini_admin=mini_admin,
        assigned_students=assigned_students
    )


@admin_routes.route('/admin/mentor/project/delete/<int:project_id>', methods=['POST'])
@login_required
def update_miniadmin_project_delete(project_id):
    if current_user.role != 'admin':
        flash_unique('Access denied.', 'danger')
        return redirect(url_for('auth_routes.login'))

    project = MiniAdminProject.query.get_or_404(project_id)

    db.session.delete(project)
    db.session.commit()

    flash_unique('Project deleted successfully.', 'success', persistent=False)
    return redirect(request.referrer or url_for('admin_routes.view_mentor_projects', miniadmin_id=project.miniadmin_id))

@admin_routes.route('/admin/mentor/project/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
def update_miniadmin_project_edit(project_id):
    if current_user.role != 'admin':
        flash_unique('Access denied.', 'danger')
        return redirect(url_for('auth_routes.login'))

    project = MiniAdminProject.query.get_or_404(project_id)
    mini_admin = User.query.get_or_404(project.miniadmin_id)

    assigned_students = [student.student_id for student in project.assigned_students]
    all_students = User.query.filter_by(role='student', miniadmin_id=mini_admin.id).all()

    if request.method == 'POST':
        project.title = request.form.get('title')
        project.description = request.form.get('description')

        # Get selected students
        selected_student_ids = set(map(int, request.form.getlist('students')))

        # Remove students not in the new selection
        MiniAdminProjectStudent.query.filter(
            MiniAdminProjectStudent.project_id == project.id,
            MiniAdminProjectStudent.student_id.notin_(selected_student_ids)
        ).delete(synchronize_session=False)

        # Add new students
        existing_student_ids = {s.student_id for s in project.assigned_students}
        new_students = selected_student_ids - existing_student_ids
        for student_id in new_students:
            db.session.add(MiniAdminProjectStudent(project_id=project.id, student_id=student_id))

        db.session.commit()
        flash_unique('Project updated successfully!', 'success', persistent=False)
        return redirect(url_for('admin_routes.view_mentor_projects', miniadmin_id=mini_admin.id))

    return render_template(
        'admin/edit_miniadmin_project.html', 
        project=project, 
        mini_admin=mini_admin, 
        all_students=all_students, 
        assigned_students=assigned_students
    )
