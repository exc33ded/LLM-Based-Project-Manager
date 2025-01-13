from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import User
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
import os

auth_routes = Blueprint('auth_routes', __name__)

@auth_routes.route('/')
def home():
    return render_template('home.html')

@auth_routes.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        name = request.form['name']
        email = request.form['email']
        rollno = request.form['rollno']
        password = request.form['password']
        role = request.form['role']
        course = request.form.get('course') if role == 'student' else None

        existing_user_by_email = User.query.filter_by(email=email).first()
        existing_user_by_rollno = User.query.filter_by(rollno=rollno).first()

        if existing_user_by_email:
            flash('Email already exists. Please use a different email.', 'danger')
            return redirect(url_for('auth_routes.register'))

        if existing_user_by_rollno:
            flash('Roll number already exists.', 'danger')
            return redirect(url_for('auth_routes.register'))

        id_card_file = request.files['id_card']
        
        id_card_filename = f"{name}_{role}_{rollno}_id_card.{id_card_file.filename.split('.')[-1]}"
        id_card_file.save(os.path.join('static/uploads/id', id_card_filename))

        hashed_password = generate_password_hash(password)
        new_user = User(
            name=name, 
            email=email, 
            rollno=rollno, 
            password=hashed_password, 
            role=role,
            course=course, 
            id_card=id_card_filename
        )

        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please wait for admin verification.', 'success')
        return redirect(url_for('auth_routes.login'))

    return render_template('register.html')

@auth_routes.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            if user.is_verified:
                login_user(user)
                flash('Login successful!', 'success')
                
                if user.role == 'mini-admin':
                    return redirect(url_for('miniadmin_routes.miniadmin_dashboard'))
                else:
                    return redirect(url_for('student_routes.student_dashboard'))
            else:
                flash('Your account is not verified yet.', 'danger')
        else:
            flash('Login unsuccessful. Please check your email and password.', 'danger')
    
    return render_template('login.html')


@auth_routes.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth_routes.login'))
