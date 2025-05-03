from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
from extensions import db, login_manager, mail
from models import User  
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv  
from waitress import serve
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

load_dotenv()

# Database configuration
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pms.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True

# Email configuration
app.config.update(
    MAIL_SERVER=os.getenv('MAIL_SERVER'),
    MAIL_PORT=int(os.getenv('MAIL_PORT')),
    MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'True').lower() == 'true', 
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD')
)
mail.init_app(app)

db.init_app(app)
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    # Query the user by user_id
    user = db.session.get(User, int(user_id))
    
    if user:
        # Check the role and log accordingly
        if user.role == 'admin':
            print(f"Admin loaded: {user.name}")
        elif user.role == 'mini-admin':
            print(f"Mini-admin loaded: {user.name}")
        elif user.role == 'student':
            print(f"Student loaded: {user.name}")
        
        return user  
    
    print("User not found.")
    return None  

# Import blueprints
from routes import auth_routes
from routes_admin import admin_routes
from routes_miniadmin import miniadmin_routes
from routes_student import student_routes

# Register blueprints
app.register_blueprint(auth_routes)
app.register_blueprint(admin_routes)
app.register_blueprint(miniadmin_routes)
app.register_blueprint(student_routes)

# Generic error handler for common HTTP errors
@app.errorhandler(400)
def bad_request(e):
    return render_template('errors/error.html', 
                          error_code="400", 
                          error_title="Bad Request", 
                          error_message="The server could not understand your request."), 400

@app.errorhandler(401)
def unauthorized(e):
    return render_template('errors/error.html', 
                          error_code="401", 
                          error_title="Unauthorized", 
                          error_message="You need to be authenticated to access this resource."), 401

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/error.html', 
                          error_code="403", 
                          error_title="Forbidden", 
                          error_message="You don't have permission to access this resource."), 403

@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/error.html', 
                          error_code="404", 
                          error_title="Page Not Found", 
                          error_message="The page you are looking for doesn't exist or has been moved."), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return render_template('errors/error.html', 
                          error_code="405", 
                          error_title="Method Not Allowed", 
                          error_message="The method is not allowed for the requested URL."), 405

@app.errorhandler(500)
def server_error(e):
    return render_template('errors/error.html', 
                          error_code="500", 
                          error_title="Server Error", 
                          error_message="Something went wrong on our end. Please try again later."), 500

# Catch-all for other server errors
@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    if isinstance(e, HTTPException):
        return e
    
    # Handle non-HTTP exceptions with a generic 500 page
    return render_template('errors/error.html', 
                          error_code="500", 
                          error_title="Server Error", 
                          error_message="An unexpected error occurred. Our team has been notified."), 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        
        # Check if admin already exists
        admin_exists = User.query.filter_by(email='admin@gmail.com', role='admin').first()
        if not admin_exists:
            hashed_password = generate_password_hash('admin')
            admin = User(
                name='Admin', 
                email='admin@gmail.com', 
                rollno='ADMIN01',  
                id_card='ID_CARD_001',  
                password=hashed_password, 
                role='admin',
                is_verified=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created!")
        else:
            print("Admin user already exists!")


    app.run(host='0.0.0.0', port=5000, debug=True)
    # serve(app, host='0.0.0.0', port=5000, threads=2)
