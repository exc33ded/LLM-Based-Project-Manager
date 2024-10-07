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
    is_verified = db.Column(db.Boolean, default=False)  # Verified by admin
    id_card = db.Column(db.String(200), nullable=False)  # Path to uploaded ID card PDF
    date_registered = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    admin_comments = db.Column(db.String(500))  # Optional comments from admin during verification

    projects = db.relationship('Project', backref='owner', lazy=True)
    miniadmin_id = db.Column(db.Integer, db.ForeignKey('users.id'))  
    assigned_students = db.relationship('User', backref=db.backref('miniadmin', remote_side=[id]), lazy=True)

    def __repr__(self):
        return f"User('{self.name}', '{self.email}', '{self.role}', Verified: {self.is_verified})"


class Project(db.Model):
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    synopsis_filename = db.Column(db.String(200), nullable=False)  # Path to synopsis PDF
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Link to student or mini-admin

    tasks = db.relationship('Task', backref='project', lazy=True)  # Tasks within the project
    
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
