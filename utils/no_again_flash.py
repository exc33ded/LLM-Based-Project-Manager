from flask import flash, session

def flash_unique(message, category="info", persistent=True):
    """
    Flash a message only if it hasn't been flashed in the current session (if persistent=True).
    
    - Persistent Messages: Prevent duplicate flashing within the same session.
    - Temporary Messages: Always allow flashing.
    """

    if 'flashed_messages' not in session:
        session['flashed_messages'] = []

    if not persistent:
        flash(message, category)
        return

    if message not in session['flashed_messages']:
        flash(message, category)
        session['flashed_messages'].append(message)
        session.modified = True 