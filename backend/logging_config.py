import logging
import logging.handlers
from flask import Flask 

# Create Flask Application
app = Flask(__name__)

# Set up structured logging configuration
class StructuredFormatter(logging.Formatter):
    def format(self, record):
        record.message = record.getMessage()
        return super().format(record)

# Add rotating file handler
file_handler = logging.handlers.RotatingFileHandler(
    'app.log', maxBytes=10*1024*1024, backupCount=5
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(StructuredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

app.logger.addHandler(file_handler)

# Add console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(StructuredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

app.logger.addHandler(console_handler)

# Example endpoint
@app.route('/')
def hello_world():
    app.logger.info('Hello World Endpoint Accessed')
    return 'Hello, World!'

if __name__ == '__main__':
    app.run()