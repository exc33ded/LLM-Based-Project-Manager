from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from models import User, Project
from extensions import db, mail
from werkzeug.security import generate_password_hash, check_password_hash
import os
from flask_mail import Message
from datetime import timedelta, datetime
import random

auth_routes = Blueprint('auth_routes', __name__)

UPLOAD_FOLDER_ID = 'static/uploads/id'
os.makedirs(UPLOAD_FOLDER_ID, exist_ok=True)

@auth_routes.route('/')
def home():
    project_count = Project.query.count()
    user_count = User.query.count()
    return render_template('home.html', project_count=project_count, user_count=user_count)

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

@auth_routes.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()

        if user:
            otp = random.randint(100000, 999999)
            session['reset_email'] = email
            session['otp'] = str(otp)
            session['otp_attempts'] = 0

            msg = Message('Your OTP for Password Reset', sender='your_email@gmail.com', recipients=[email])
            msg.body = f'Your OTP is: {otp}'
            mail.send(msg)

            flash('OTP sent to your email. Please verify.', 'info')
            return redirect(url_for('auth_routes.verify_otp'))

        flash('Email not found.', 'danger')

    return render_template('forgot_password.html')

@auth_routes.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        entered_otp = request.form['otp']
        attempts = session.get('otp_attempts', 0)

        if attempts >= 3:
            flash('Maximum attempts exceeded.', 'danger')
            return redirect(url_for('auth_routes.forgot_password'))

        if entered_otp == session.get('otp'):
            session.pop('otp_attempts', None)
            return redirect(url_for('auth_routes.reset_password'))
        else:
            session['otp_attempts'] = attempts + 1
            flash(f'Incorrect OTP. Attempts left: {2 - attempts}', 'danger')

    return render_template('verify_otp.html')

@auth_routes.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        new_password = request.form['password']
        confirm_password = request.form['confirm_password']
        email = session.get('reset_email')

        if new_password != confirm_password:
            flash("Passwords do not match. Please try again.", "danger")
            return redirect(url_for('auth_routes.reset_password'))

        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_password)
            db.session.commit()

            session.pop('reset_email', None)
            flash('Password changed successfully. Please login.', 'success')
            return redirect(url_for('auth_routes.login'))

    return render_template('reset_password.html')


@auth_routes.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth_routes.login'))
