from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user, logout_user
from models import Project, db, Task, User
from werkzeug.utils import secure_filename
import os
from datetime import datetime

miniadmin_routes = Blueprint('miniadmin_routes', __name__)

@miniadmin_routes.route('/dashboard', methods=['GET', 'POST'])
@login_required
def miniadmin_dashboard():
    if current_user.role != 'mini-admin':
        flash('Access denied.', 'danger')
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

# ------------------------------ Managing Project with Tasks for the students ----------------------------------

def check_task_status(task):
    if task.due_date.date() < datetime.now().date():
        if task.status != 'Finished':
            task.status = 'Backlog'
            db.session.commit()
            flash(f"Task '{task.title}' moved to Backlog due to overdue date.", 'warning')
            
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
    flash(f'Task moved to {new_status} successfully!', 'success')
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
        flash('Task added successfully!', 'success')
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
        flash('Task updated successfully!', 'success')
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

    flash('Task deleted successfully!', 'success')
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
    flash(f"Project '{project.title}' has been deleted.", 'success')
    return redirect(url_for('miniadmin_routes.view_projects'))

@miniadmin_routes.route('/miniadmin/logout')
@login_required
def miniadmin_logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth_routes.login'))