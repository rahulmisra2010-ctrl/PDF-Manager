import os
from your_flask_app import create_app

# Set the environment variable for Flask
os.environ['FLASK_ENV'] = 'production'

app = create_app()

if __name__ == '__main__':
    app.run()