from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from extensions import db

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    rollno = db.Column(db.String(6), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(10), nullable=False, default='student')  # 'admin', 'mini-admin', 'student'
    is_verified = db.Column(db.Boolean, default=False)
    id_card = db.Column(db.String(200), nullable=False)
    date_registered = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    admin_comments = db.Column(db.String(500))
    course = db.Column(db.String(50), nullable=True) 

    projects = db.relationship('Project', backref='owner', lazy=True)
    miniadmin_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_students = db.relationship('User', backref=db.backref('miniadmin', remote_side=[id]), lazy=True)

    # Relationship to MiniAdminProject
    miniadmin_projects = db.relationship('MiniAdminProject', backref='miniadmin', lazy=True)

    # Forget Password Token
    otp = db.Column(db.String(6))
    otp_created_at = db.Column(db.DateTime)
    otp_attempts = db.Column(db.Integer, default=0)

class Project(db.Model):
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    synopsis_filename = db.Column(db.String(200), nullable=False)  # Path to synopsis PDF
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Link to student or mini-admin

    summary = db.Column(db.Text, nullable=True)  # AI-generated project summary
    category = db.Column(db.String(50), nullable=True) 

    tasks = db.relationship('Task', backref='project', cascade="all, delete", lazy=True)  # Tasks within the project
    long_term_memory = db.relationship('LongTermMemory', backref='project', cascade="all, delete", lazy=True)

    def __repr__(self):
        return f"Project('{self.title}', '{self.start_date}')"

class Task(db.Model):
    __tablename__ = 'tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False) 
    due_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'To Be Progressed', 'In Progress', 'Completed'
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    def __repr__(self):
        return f"Task('{self.title}', '{self.status}', '{self.due_date}')"

class LongTermMemory(db.Model):
    __tablename__ = 'long_term_memory'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)  # Link to project
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Link to user
    chat_content = db.Column(db.Text, nullable=False)  # Chat response or conversation
    important_content = db.Column(db.Text, nullable=True)  # AI-detected important info
    importance_score = db.Column(db.Float, default=0.5)  # AI-assigned score (0.0 to 1.0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # Timestamp for when the chat was stored

    def __repr__(self):
        return f"LongTermMemory(Project ID: {self.project_id}, User ID: {self.user_id}, Timestamp: {self.timestamp})"

class MiniAdminProject(db.Model):
    __tablename__ = 'miniadmin_projects'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    miniadmin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Link to mini-admin
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationship to MiniAdminProjectTask
    tasks = db.relationship('MiniAdminProjectTask', backref='miniadmin_project', cascade="all, delete", lazy=True)

    # Add cascading delete on the relationship with MiniAdminProjectStudent
    assigned_students = db.relationship('MiniAdminProjectStudent', backref='project', cascade="all, delete", lazy=True)

    def __repr__(self):
        return f"MiniAdminProject('{self.title}', '{self.miniadmin_id}', '{self.created_at}')"


class MiniAdminProjectTask(db.Model):
    __tablename__ = 'miniadmin_project_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False) 
    due_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'To Be Progressed', 'In Progress', 'Completed'
    miniadmin_project_id = db.Column(db.Integer, db.ForeignKey('miniadmin_projects.id'), nullable=False)

    def __repr__(self):
        return f"MiniAdminProjectTask('{self.title}', '{self.status}', '{self.due_date}')"


class MiniAdminProjectStudent(db.Model):
    __tablename__ = 'miniadmin_project_students'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('miniadmin_projects.id'), nullable=False)  # Link to mini-admin project
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Link to student

    student = db.relationship('User', backref='projects_assigned')

    def __repr__(self):
        return f"MiniAdminProjectStudent(Project ID: {self.project_id}, Student ID: {self.student_id})"
