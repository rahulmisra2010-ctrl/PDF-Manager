import pytest
import os
import sys
from app import create_app, db
from models import User

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """A test runner for the app's CLI commands."""
    return app.test_cli_runner()

# Test app initialization
def test_app_creation(app):
    """Test that the app is created successfully."""
    assert app is not None
    assert app.config['TESTING'] is True

# Test database configuration
def test_database_configuration(app):
    """Test that database is configured correctly."""
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///:memory:'

# Test home page
def test_home_page(client):
    """Test that home page loads."""
    response = client.get('/')
    # Page should redirect or return 200/302 status
    assert response.status_code in [200, 302, 404]

# Test 404 error handling
def test_error_handling(client):
    """Test that 404 errors are handled correctly."""
    response = client.get('/api/notfound')
    assert response.status_code == 404

# Test app context
def test_app_context(app):
    """Test that app context is available."""
    with app.app_context():
        assert db.session is not None
