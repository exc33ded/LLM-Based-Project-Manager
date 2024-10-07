from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
from extensions import db, login_manager
from models import User  # Only User is imported now
from werkzeug.security import generate_password_hash

app = Flask(__name__)

app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pms.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True

db.init_app(app)
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    # Query the user by user_id
    user = User.query.get(int(user_id))
    
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
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created!")
        else:
            print("Admin user already exists!")


    app.run(debug=True)
