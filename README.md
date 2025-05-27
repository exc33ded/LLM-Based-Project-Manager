# Advanced-Project-Manager-for-AMU

## Overview

**Advanced-Project-Manager-for-AMU** is a multi-role project management system with authentication and verification features. It allows users to manage multiple projects, generate tasks, and track progress while leveraging AI for enhanced project summaries and task management. Each project has its own memory-based chat feature, allowing for efficient project-specific communication and task delegation.

## Features

- **User Authentication and Verification**: Secure login system using user ID for authentication and verification.
- **Multi-Role System**: Supports various roles such as admin, project manager, and worker, each with specific permissions.
- **Task Generation and Management**: The system generates tasks that represent worker progress, making it easy to track and manage project workflows.
- **Project Summary Generation**: Each project has an AI-generated summary that helps manage tasks and guides the user.
- **Memory-Based Chat**: Projects come with a built-in chat application that retains the conversation history, helping users communicate and manage projects more effectively.
- **Unique Project Memory**: Each project retains its own memory, allowing for unique interactions based on the specific project's history and needs.

## How It Works

1. **User Verification**: After logging in, users are authenticated using their user ID.
2. **Project Creation**: Users can create projects, each identified by a unique combination of user ID and project ID.
3. **Task and Project Management**: Users can generate tasks, manage them, and use AI to provide project summaries that guide task execution.
4. **Project-Specific Memory**: Each project has its own memory-based chat feature, allowing users to communicate specifically for that project, with the system retaining the project's history.
5. **AI Interaction**: The AI uses the project summary to manage tasks, providing intelligent recommendations and tracking progress efficiently.

## Requirements

- **Python Version**: This project requires Python 3.12.4. Ensure you have this version installed before proceeding.
- Other dependencies are listed in `requirements.txt`.

To check your Python version, run:
```bash
python --version
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/exc33ded/Advanced-Project-Manager-for-AMU.git
```
2. Navigate to the project directory:
```bash
cd Advanced-Project-Manager-for-AMU
```
3. Install the required dependencies:
```bash
pip install -r requirements.txt
```
4. Set up the database and start the server:
```bash
python app.py
```

## Usage

1. **Sign Up / Log In**  
   Register as a new user or log in with your existing credentials.

2. **Create Projects**  
   - Navigate to the project creation page.  
   - Enter the following details:  
     - **User ID**: Your unique user identifier.  
     - **Project ID**: A unique identifier for the project.  
     - **Project Name**: A descriptive name for the project.  
     - **Project Summary**: A brief summary of the project, which will guide the AI.  
   - Click the "Submit" button to create the project.  
   - Once created, your project will appear in the project list table.

3. **Manage Tasks**  
   - Access a project from the project list by clicking its name.  
   - Generate and assign tasks to track worker progress.  
   - Tasks are updated and saved in the project’s dashboard.

4. **Start Chat**  
   - Click on the chat feature within a project.  
   - Start a conversation with the memory-based chat system.  
   - The chat stores project-specific history, allowing for contextual discussions.

5. **Stop Chat and Save History**  
   - Stop the chat when finished.  
   - The conversation history is automatically saved to the database for future reference.  

6. **View and Track Progress**  
   - Revisit the project to view saved chats and tasks.  
   - Use the system to adjust or refine tasks as the project evolves.
