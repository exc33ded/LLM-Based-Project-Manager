from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from models import Project, db, Task
from werkzeug.utils import secure_filename
import os
from datetime import datetime

student_routes = Blueprint('student_routes', __name__)

UPLOAD_FOLDER = 'static/uploads/synopsis'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@student_routes.route('/student/dashboard')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    return render_template('student/student_dashboard.html', user=current_user)

@student_routes.route('/student/projects')
@login_required
def view_projects():
    if current_user.role != 'student':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    projects = Project.query.filter_by(student_id=current_user.id).all()
    return render_template('student/view_projects.html', projects=projects)

@student_routes.route('/student/projects/add', methods=['GET', 'POST'])
@login_required
def add_project():
    if current_user.role != 'student':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    
    if request.method == 'POST':
        title = request.form['title']
        start_date_str = request.form['start_date']
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') 
        synopsis = request.files['synopsis']
        
        unique_synopsis_filename = f"{current_user.name}_{current_user.rollno}_{title}_synopsis.{synopsis.filename.split('.')[-1]}"
        synopsis_filename = secure_filename(unique_synopsis_filename)
        synopsis.save(os.path.join(UPLOAD_FOLDER, synopsis_filename))

        project = Project(title=title, start_date=start_date, synopsis_filename=synopsis_filename, student_id=current_user.id)
        db.session.add(project)
        db.session.commit()

        flash("Project added successfully!", "success")
        return redirect(url_for('student_routes.view_projects'))

    return render_template('student/add_project.html')

@student_routes.route('/student/projects/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    if current_user.role != 'student':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    project = Project.query.get_or_404(project_id)

    if project.student_id != current_user.id:
        flash('Unauthorized to edit this project', 'danger')
        return redirect(url_for('student_routes.view_projects'))

    if request.method == 'POST':
        title = request.form['title']
        start_date_str = request.form['start_date']
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') 
        synopsis = request.files.get('synopsis')
        if synopsis:
            synopsis_filename = secure_filename(synopsis.filename)
            synopsis.save(os.path.join(UPLOAD_FOLDER, synopsis_filename))
            project.synopsis_filename = synopsis_filename

        project.title = title
        project.start_date = start_date
        
        db.session.commit()
        flash("Project updated successfully!", "success")
        return redirect(url_for('student_routes.view_projects'))

    return render_template('student/edit_project.html', project=project)

@student_routes.route('/student/projects/delete/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    if current_user.role != 'student':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    project = Project.query.get_or_404(project_id)

    if project.student_id != current_user.id:
        flash('Unauthorized to delete this project', 'danger')
        return redirect(url_for('student_routes.view_projects'))

    db.session.delete(project)
    db.session.commit()
    flash("Project deleted successfully!", "success")
    return redirect(url_for('student_routes.view_projects'))

@student_routes.route('/student/projects/archive')
@login_required
def project_archive():
    if current_user.role != 'student':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    if not current_user.is_verified:
        flash("Only verified students can access the project archive.", "danger")
        return redirect(url_for('student_routes.view_projects'))

    projects = Project.query.all()
    return render_template('student/project_archive.html', projects=projects)


# ------------------  From here I will start with the tasks  -----------------------------------
def check_task_status(task):
    if task.due_date.date() < datetime.now().date():
        if task.status != 'Finished':
            task.status = 'Backlog'
            db.session.commit()
            flash(f"Task '{task.title}' moved to Backlog due to overdue date.", 'warning')
            
@student_routes.route('/project/<int:project_id>/tasks')
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

    return render_template('student/tasks.html', project=project,
                           backlog_tasks=backlog_tasks, in_progress_tasks=in_progress_tasks,
                           progressed_tasks=progressed_tasks, finished_tasks=finished_tasks)
    
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

        flash('New task added successfully!', 'success')
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
                flash(f"Task '{task.title}' moved to Backlog due to overdue date.", 'warning')

        db.session.commit()
        flash('Task updated successfully!', 'success')
        return redirect(url_for('student_routes.view_tasks', project_id=project_id))

    return render_template('student/edit_task.html', task=task)

@student_routes.route('/task/<int:task_id>/change_status', methods=['POST'])
@login_required
def change_task_status(task_id):
    task = Task.query.get_or_404(task_id)
    project_id = task.project_id
    project = Project.query.get_or_404(project_id)

    if current_user.id != project.student_id:
        flash("You are not authorized to change tasks in this project.", 'danger')
        return redirect(url_for('student_routes.project_archive'))

    new_status = request.form['status']
    task.status = new_status
    db.session.commit()

    flash(f"Task status updated to '{new_status}'", 'success')
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
    flash('Task deleted successfully!', 'success')
    return redirect(url_for('student_routes.view_tasks', project_id=project_id))