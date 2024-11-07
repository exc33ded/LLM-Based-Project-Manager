from flask import Blueprint, render_template, redirect, url_for, flash, request
from models import User, Project, Task
from extensions import db
from flask_login import login_user, login_required, current_user, logout_user
from werkzeug.security import check_password_hash
from datetime import datetime
import random
from werkzeug.utils import secure_filename
import os

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
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_routes.admin_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    return render_template('admin_login.html')


@admin_routes.route('/admin/dashboard', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
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
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    mini_admins = User.query.filter_by(role='mini-admin').all()
    
    return render_template('admin/admin_assignments.html', mini_admins=mini_admins)

@admin_routes.route('/admin/verify_users')
@login_required
def verify_users():
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    pending_users = User.query.filter_by(is_verified=False).all()
    return render_template('admin/verify_users.html', pending_users=pending_users)

@admin_routes.route('/admin/verify_users/<int:user_id>', methods=['GET', 'POST'])
@login_required
def verify_user(user_id):
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        admin_comments = request.form.get('admin_comments')
        verification_status = request.form.get('verification_status')

        user.admin_comments = admin_comments

        if verification_status == 'verify':
            user.is_verified = True
            flash(f"User {user.name} has been verified.", 'success')
        elif verification_status == 'not_verify':
            user.is_verified = False
            flash(f"User {user.name} has not been verified.", 'danger')

        db.session.commit() 

        return redirect(url_for('admin_routes.verify_users'))

    return render_template('admin/verify_user.html', user=user)

@admin_routes.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.name} has been deleted.", 'success')
    else:
        flash('User not found.', 'danger')
    return redirect(url_for('admin_routes.verify_users'))

@admin_routes.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin_routes.admin_login'))

# ------------------------------ Managing Project with Tasks for the students ----------------------------------

@admin_routes.route('/admin/projects/create/<int:user_id>', methods=['GET', 'POST'])
@login_required
def add_project(user_id):
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        title = request.form['title']
        start_date_str = request.form['start_date']
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') 
        synopsis = request.files['synopsis']
        num = random.randint(1, 10000)
        
        unique_synopsis_filename = f"{current_user.name}_{current_user.rollno}__{num}__{title}_synopsis.{synopsis.filename.split('.')[-1]}"
        synopsis_filename = secure_filename(unique_synopsis_filename)
        synopsis.save(os.path.join(UPLOAD_FOLDER, synopsis_filename))

        new_project = Project(title=title, start_date=start_date, synopsis_filename=synopsis_filename, student_id=user.id)
        db.session.add(new_project)
        db.session.commit()

        flash("Project added successfully!", "success")

        return redirect(url_for('admin_routes.view_student_projects', user_id=user.id))

    return render_template('admin/create_project.html', user=user)

def check_task_status(task):
    if task.due_date.date() < datetime.now().date():
        if task.status != 'Finished':
            task.status = 'Backlog'
            db.session.commit()
            flash(f"Task '{task.title}' moved to Backlog due to overdue date.", 'warning')

@admin_routes.route('/admin/projects')
@login_required
def view_projects():
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    users = User.query.all()
    student_projects = [(user, len(user.projects)) for user in users if user.role == 'student']
    
    return render_template('admin/view_projects.html', student_projects=student_projects)

@admin_routes.route('/admin/projects/<int:user_id>')
@login_required
def view_student_projects(user_id):
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    user = User.query.get_or_404(user_id)
    projects = Project.query.filter_by(student_id=user.id).all()
    
    return render_template('admin/view_student_projects.html', user=user, projects=projects)

@admin_routes.route('/admin/projects/<int:project_id>/tasks', methods=['GET'])
@login_required
def view_project_tasks(project_id):
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
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
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    task = Task.query.get_or_404(task_id)
    new_status = request.form.get('status')  # Get the new status from the form
    task.status = new_status

    db.session.commit()
    flash(f'Task moved to {new_status} successfully!', 'success')
    return redirect(url_for('admin_routes.view_project_tasks', project_id=task.project_id))

@admin_routes.route('/admin/projects/tasks/add/<int:project_id>', methods=['GET', 'POST'])
@login_required
def add_task(project_id):
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    project = Project.query.get_or_404(project_id)  # Fetch the project by ID

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
        return redirect(url_for('admin_routes.view_project_tasks', project_id=project_id))

    return render_template('admin/add_task.html', project=project)


@admin_routes.route('/admin/projects/tasks/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    if current_user.role != 'admin':
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
        return redirect(url_for('admin_routes.view_project_tasks', project_id=task.project_id))

    return render_template('admin/edit_task.html', task=task)

@admin_routes.route('/admin/projects/tasks/delete/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()

    flash('Task deleted successfully!', 'success')
    return redirect(url_for('admin_routes.view_project_tasks', project_id=task.project_id))

@admin_routes.route('/admin/projects/delete/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    if current_user.role != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('auth_routes.login'))

    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash(f"Project '{project.title}' has been deleted.", 'success')
    return redirect(url_for('admin_routes.view_projects'))


# ------------------------ Mini-Admin Work --------------------------------------------

@admin_routes.route('/admin/assign_students', methods=['GET', 'POST'])
@login_required
def assign_students():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('auth_routes.login'))

    # Fetch mini-admins and unassigned students
    mini_admins = User.query.filter_by(role='mini-admin', is_verified=True).all()
    students = User.query.filter_by(role='student', miniadmin_id=None, is_verified=True).all()

    if request.method == 'POST':
        selected_miniadmin = request.form.get('miniadmin_id')

        if not selected_miniadmin:
            flash('Mini-admin selection is required!', 'danger')
            return redirect(url_for('admin_routes.assign_students'))

        selected_students = request.form.getlist('students')

        miniadmin = User.query.get(selected_miniadmin)
        for student_id in selected_students:
            student = User.query.get(student_id)
            student.miniadmin_id = miniadmin.id
            db.session.commit()

        flash('Students assigned successfully!', 'success')

        return redirect(url_for('admin_routes.assign_students'))

    return render_template('admin/assign_students.html', mini_admins=mini_admins, students=students)



@admin_routes.route('/admin/unassign_student', methods=['POST'])
@login_required
def unassign_student():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
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
            flash(f'Student {student.name} has been unassigned successfully!', 'success')
        else:
            flash('Mini-admin not found!', 'danger')
    else:
        flash('Student not found!', 'danger')

    return redirect(url_for('admin_routes.admin_dashboard'))  # Redirect to the admin dashboard after unassignment


@admin_routes.route('/admin/unassign_all', methods=['POST'])
@login_required
def unassign_all():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('auth_routes.login'))

    miniadmin_id = request.form.get('miniadmin_id')

    if miniadmin_id:
        # Fetch the mini-admin to validate existence
        miniadmin = User.query.get(miniadmin_id)
        
        if miniadmin:  # Ensure miniadmin is found
            # Fetch all students assigned to the mini-admin
            students = User.query.filter_by(miniadmin_id=miniadmin_id).all()
            
            # Unassign each student
            for student in students:
                student.miniadmin_id = None
                # Remove from mini-admin's assigned_students
                if student in miniadmin.assigned_students:
                    miniadmin.assigned_students.remove(student)

            db.session.commit()
            flash('All students unassigned successfully!', 'success')
        else:
            flash('Mini-admin not found!', 'danger')
    else:
        flash('Invalid request!', 'danger')

    return redirect(url_for('admin_routes.admin_dashboard')) 
