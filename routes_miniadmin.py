from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user, logout_user
from models import Project, db, Task, User, MiniAdminProject, MiniAdminProjectStudent, MiniAdminProjectTask
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from utils.task_generation import generate_dynamic_coding_tasks
from utils.no_again_flash import flash_unique
import json

miniadmin_routes = Blueprint('miniadmin_routes', __name__)

@miniadmin_routes.route('/dashboard', methods=['GET', 'POST'])
@login_required
def miniadmin_dashboard():
    if current_user.role != 'mini-admin':
        flash_unique('Access denied.', 'danger', persistent=False)
        return redirect(url_for('auth_routes.login'))

    # Get assigned students for the mini-admin
    assigned_students = current_user.assigned_students
    assigned_students_count = len(assigned_students)

    # Get total projects assigned to mini-admin's students
    total_projects = sum(len(student.projects) for student in assigned_students)

    # Get the total tasks categorized by their status
    backlog_tasks_count = Task.query.filter_by(status='Backlog').count()
    in_progress_tasks_count = Task.query.filter_by(status='In Progress').count()
    progressed_tasks_count = Task.query.filter_by(status='Progressed').count()
    finished_tasks_count = Task.query.filter_by(status='Finished').count()

    # If a specific project is selected, filter the tasks for that project
    project_id = request.args.get('project_id', None)
    if project_id:
        project = Project.query.get_or_404(project_id)
        tasks = Task.query.filter_by(project_id=project_id).all()

        # Categorize tasks by status
        backlog_tasks_count = len([task for task in tasks if task.status == 'Backlog'])
        in_progress_tasks_count = len([task for task in tasks if task.status == 'In Progress'])
        progressed_tasks_count = len([task for task in tasks if task.status == 'Progressed'])
        finished_tasks_count = len([task for task in tasks if task.status == 'Finished'])

    return render_template(
        'miniadmin/miniadmin_dashboard.html',
        assigned_students_count=assigned_students_count,
        total_projects=total_projects,
        backlog_tasks_count=backlog_tasks_count,
        in_progress_tasks_count=in_progress_tasks_count,
        progressed_tasks_count=progressed_tasks_count,
        finished_tasks_count=finished_tasks_count,
        assigned_students=assigned_students  # Send the list of assigned students
    )

# ------------------------------ Managing Mentor Project with students  ----------------------------------

@miniadmin_routes.route('/my-projects')
@login_required
def my_projects():
    if current_user.role != 'mini-admin':
        flash_unique('Access denied.', 'danger', persistent=False)
        return redirect(url_for('auth_routes.login'))

    # Fetch all projects for the current mini-admin
    projects = MiniAdminProject.query.filter_by(miniadmin_id=current_user.id).all()

    # For each project, fetch the assigned students
    projects_with_assignments = []
    for project in projects:
        assignments = MiniAdminProjectStudent.query.filter_by(project_id=project.id).all()
        students = [assignment.student for assignment in assignments]
        projects_with_assignments.append({'project': project, 'students': students})

    return render_template('miniadmin/my_projects.html', projects_with_assignments=projects_with_assignments)


@miniadmin_routes.route('/create-project', methods=['GET', 'POST'])
@login_required
def create_project():
    if current_user.role != 'mini-admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    # Fetch students assigned to this mini-admin
    students = User.query.filter_by(role='student').filter_by(miniadmin_id=current_user.id).all()

    if request.method == 'POST':
        title = request.form.get('project_name')  
        description = request.form.get('project_summary')  
        assigned_students = request.form.getlist('assigned_students')
        generate_ai_tasks = request.form.get("generate_ai_tasks") == "on"

        if not title or not description:
            flash("Project name and summary are required!", "danger")
            return redirect(url_for('miniadmin_routes.create_project'))

        # Create a new project under MiniAdminProject model
        new_project = MiniAdminProject(
            title=title,
            description=description,
            miniadmin_id=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(new_project)
        db.session.commit()

        # Assign selected students to this project
        for student_id in assigned_students:
            project_student = MiniAdminProjectStudent(
                project_id=new_project.id, 
                student_id=int(student_id)
            )
            db.session.add(project_student)

        db.session.commit()

        if generate_ai_tasks:
            try:
                task_data = json.loads(generate_dynamic_coding_tasks(description))
                # print(task_data)
                for task_title, task_details in task_data.items():
                    task = MiniAdminProjectTask(
                        title=task_title,
                        description=task_details['Task Description'],
                        due_date=datetime.strptime(task_details['Date'], '%Y-%m-%d'),
                        status='In Progress',
                        miniadmin_project_id=new_project.id
                    )
                    db.session.add(task)
                db.session.commit()
                flash_unique("Project and AI-generated tasks created successfully!", "success", persistent=False)
            
            except Exception as e:
                flash_unique(f"AI Task generation failed: {e}", "danger", persistent=False)

        flash_unique(f"Project '{title}' created successfully!", "success", persistent=False)
        return redirect(url_for('miniadmin_routes.my_projects'))

    return render_template('miniadmin/create_project.html', students=students)

@miniadmin_routes.route('/miniadmin/project/<int:project_id>/assign', methods=['GET', 'POST'])
@login_required
def assign_student(project_id):
    project = MiniAdminProject.query.get_or_404(project_id)
    
    # Ensure user is a mini-admin and the project belongs to them
    if current_user.role != 'mini-admin' or current_user.id != project.miniadmin_id:
        return redirect(url_for('home'))
    
    # Get students assigned to the current mini-admin
    students = User.query.filter_by(role='student', miniadmin_id=current_user.id).all()
    
    # Get all students assigned to the project
    assigned_students = MiniAdminProjectStudent.query.filter_by(project_id=project.id).all()
    assigned_student_ids = [assignment.student_id for assignment in assigned_students]

    # Get the actual student objects from assigned student ids
    assigned_students_list = User.query.filter(User.id.in_(assigned_student_ids)).all()

    # Get the return URL from the query parameters (default to a fallback URL if not provided)
    return_url = request.args.get('return_url', url_for('miniadmin_routes.my_projects'))

    if request.method == 'POST':
        student_id = request.form.get('student_id')
        if student_id and int(student_id) not in assigned_student_ids:
            # Assign the student
            assignment = MiniAdminProjectStudent(project_id=project.id, student_id=int(student_id))
            db.session.add(assignment)
            db.session.commit()
            return redirect(url_for('miniadmin_routes.assign_student', project_id=project.id, return_url=return_url))

    # Handle unassign request
    if request.args.get('unassign'):
        student_id_to_unassign = request.args.get('unassign')
        assignment_to_remove = MiniAdminProjectStudent.query.filter_by(project_id=project.id, student_id=student_id_to_unassign).first()
        if assignment_to_remove:
            db.session.delete(assignment_to_remove)
            db.session.commit()
        return redirect(url_for('miniadmin_routes.assign_student', project_id=project.id, return_url=return_url))

    return render_template(
        'miniadmin/assign_student.html', 
        project=project, 
        students=students, 
        assigned_student_ids=assigned_student_ids,
        assigned_students=assigned_students_list,
        return_url=return_url  # Pass the return URL to the template
    )

# ------------------------------ Managing Project with Tasks for the students ----------------------------------

def check_task_status(task):
    if task.due_date.date() < datetime.now().date():
        if task.status != 'Finished':
            task.status = 'Backlog'
            db.session.commit()
            flash_unique(f"Task '{task.title}' moved to Backlog due to overdue date.", 'warning')
            
@miniadmin_routes.route('/miniadmin/projects', methods=['GET'])
@login_required
def view_projects():
    if current_user.role != 'mini-admin':
        flash('Access denied.', 'danger')
        
    assigned_students = current_user.assigned_students  
    student_projects = [(student, len(student.projects)) for student in assigned_students]

    return render_template('miniadmin/view_projects.html', student_projects=student_projects)
    
@miniadmin_routes.route('/miniadmin/projects/<int:user_id>')
@login_required
def view_student_projects(user_id):
    if current_user.role != 'mini-admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    user = User.query.get_or_404(user_id)
    projects = Project.query.filter_by(student_id=user_id).all()
    
    return render_template('miniadmin/view_student_projects.html', user=user, projects=projects)


@miniadmin_routes.route('/miniadmin/projects/<int:project_id>/tasks', methods=['GET'])
@login_required
def view_project_tasks(project_id):
    if current_user.role != 'mini-admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    user_id = request.args.get('user_id')
    print(user_id)
    user = User.query.get_or_404(user_id) if user_id else None

    project = Project.query.get_or_404(project_id)

    if project.student_id not in [student.id for student in current_user.assigned_students]:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('miniadmin_routes.view_students'))

    tasks = Task.query.filter_by(project_id=project.id).all()

    for task in tasks:
        check_task_status(task)

    # Categorize tasks by status
    backlog_tasks = [task for task in tasks if task.status == 'Backlog']
    in_progress_tasks = [task for task in tasks if task.status == 'In Progress']
    progressed_tasks = [task for task in tasks if task.status == 'Progressed']
    finished_tasks = [task for task in tasks if task.status == 'Finished']

    return render_template('miniadmin/view_project_tasks.html', user=user, project=project,
                           backlog_tasks=backlog_tasks,
                           in_progress_tasks=in_progress_tasks,
                           progressed_tasks=progressed_tasks,
                           finished_tasks=finished_tasks)


@miniadmin_routes.route('/miniadmin/projects/tasks/move/<int:task_id>', methods=['POST'])
@login_required
def move_task(task_id):
    if current_user.role != 'mini-admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    task = Task.query.get_or_404(task_id)
    new_status = request.form.get('status')  
    task.status = new_status

    db.session.commit()
    flash_unique(f'Task moved to {new_status} successfully!', 'success', persistent=False)
    return redirect(url_for('miniadmin_routes.view_project_tasks', project_id=task.project_id))

@miniadmin_routes.route('/miniadmin/projects/tasks/add/<int:project_id>', methods=['GET', 'POST'])
@login_required
def add_task(project_id):
    if current_user.role != 'mini-admin':
        flash('Unauthorized access', 'danger')
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
        return redirect(url_for('miniadmin_routes.view_project_tasks', project_id=project_id))

    return render_template('miniadmin/add_task.html', project=project)

@miniadmin_routes.route('/miniadmin/projects/tasks/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    if current_user.role != 'mini-admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    task = Task.query.get_or_404(task_id)

    if request.method == 'POST':
        task.title = request.form['title']
        task.description = request.form['description']
   
        due_date_str = request.form['due_date']
        task.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() 

        db.session.commit()
        flash_unique('Task updated successfully!', 'success', persistent=False)
        return redirect(url_for('miniadmin_routes.view_project_tasks', project_id=task.project_id))

    return render_template('miniadmin/edit_task.html', task=task)

@miniadmin_routes.route('/miniadmin/projects/tasks/delete/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    if current_user.role != 'mini-admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()

    flash_unique('Task deleted successfully!', 'success', persistent=False)
    return redirect(url_for('miniadmin_routes.view_project_tasks', project_id=task.project_id))

@miniadmin_routes.route('/miniadmin/projects/delete/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    if current_user.role != 'mini-admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash_unique(f"Project '{project.title}' has been deleted.", 'success', persistent=False)
    return redirect(url_for('miniadmin_routes.view_projects'))

@miniadmin_routes.route('/miniadmin/my-projects/delete/<int:project_id>', methods=['POST'])
@login_required
def delete_miniadmin_project(project_id):
    if current_user.role != 'mini-admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    project = MiniAdminProject.query.filter_by(id=project_id, miniadmin_id=current_user.id).first()

    if not project:
        flash_unique('Project not found or unauthorized access.', 'danger', persistent=False)
        return redirect(url_for('miniadmin_routes.my_projects'))

    db.session.delete(project)
    db.session.commit()

    flash_unique(f"Project '{project.title}' has been deleted.", 'success', persistent=False)
    return redirect(url_for('miniadmin_routes.my_projects'))


@miniadmin_routes.route('/miniadmin/logout')
@login_required
def miniadmin_logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth_routes.login'))

## ------------------------------------------------------Mini - Admin Task---------------------------------------------------------

@miniadmin_routes.route('/miniadmin/project/<int:project_id>/task/create', methods=['GET', 'POST'])
@login_required
def create_task_for_miniadmin_project(project_id):
    project = MiniAdminProject.query.get_or_404(project_id)

    if request.method == 'POST':
        task_title = request.form['title']
        task_description = request.form['description']
        task_due_date = datetime.strptime(request.form['due_date'], '%Y-%m-%d')
        task_status = 'In Progress'  

        new_task = MiniAdminProjectTask(
            title=task_title,
            description=task_description,
            due_date=task_due_date,
            status=task_status,
            miniadmin_project_id=project.id
        )

        db.session.add(new_task)
        db.session.commit()

        flash_unique('New task added successfully!', 'success', persistent=False)
        return redirect(url_for('miniadmin_routes.view_tasks_for_miniadmin_project', project_id=project.id))

    return render_template('miniadmin/add_task_for_project.html', project=project)


@miniadmin_routes.route('/miniadmin/project/<int:project_id>/task/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task_for_miniadmin_project(project_id, task_id):
    task = MiniAdminProjectTask.query.get_or_404(task_id)
    project = MiniAdminProject.query.get_or_404(project_id)

    if request.method == 'POST':
        task.title = request.form['title']
        task.description = request.form['description']
        task.due_date = datetime.strptime(request.form['due_date'], '%Y-%m-%d')

        db.session.commit()
        flash_unique('Task updated successfully!', 'success', persistent=False)
        flash(
            f"Task '{task.title}' has been moved to {task.status} due to overdue date.",
            'warning' if task.due_date.date() < datetime.now().date() else 'success'
        )
        return redirect(url_for('miniadmin_routes.view_tasks_for_miniadmin_project', project_id=project_id))

    return render_template('miniadmin/edit_task_for_project.html', task=task, project=project)


@miniadmin_routes.route('/miniadmin/project/<int:project_id>/task/delete/<int:task_id>', methods=['POST'])
@login_required
def delete_task_for_miniadmin_project(project_id, task_id):
    task = MiniAdminProjectTask.query.get_or_404(task_id)

    db.session.delete(task)
    db.session.commit()
    
    flash_unique('Task deleted successfully!', 'success', persistent=False)
    return redirect(url_for('miniadmin_routes.view_tasks_for_miniadmin_project', project_id=project_id))


@miniadmin_routes.route('/miniadmin/project/<int:project_id>/tasks', methods=['GET'])
@login_required
def view_tasks_for_miniadmin_project(project_id):
    project = MiniAdminProject.query.get_or_404(project_id)
    
    tasks = MiniAdminProjectTask.query.filter_by(miniadmin_project_id=project.id).all()

    # Categorize tasks by status
    backlog_tasks = [task for task in tasks if task.status == 'Backlog']
    in_progress_tasks = [task for task in tasks if task.status == 'In Progress']
    progressed_tasks = [task for task in tasks if task.status == 'Progressed']
    finished_tasks = [task for task in tasks if task.status == 'Finished']

    return render_template(
        'miniadmin/view_tasks_for_project.html',
        project=project,
        backlog_tasks=backlog_tasks,
        in_progress_tasks=in_progress_tasks,
        progressed_tasks=progressed_tasks,
        finished_tasks=finished_tasks
    )

@miniadmin_routes.route('/miniadmin/project/<int:project_id>/task/move/<int:task_id>', methods=['POST'])
@login_required
def move_task_status(project_id, task_id):
    if current_user.role != 'mini-admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    
    task = MiniAdminProjectTask.query.get_or_404(task_id)
    new_status = request.form.get('status')  
    task.status = new_status
    
    db.session.commit()

    flash_unique(f'Task moved to {new_status} successfully!', 'success', persistent=False)
    return redirect(url_for('miniadmin_routes.view_tasks_for_miniadmin_project', project_id=project_id))
