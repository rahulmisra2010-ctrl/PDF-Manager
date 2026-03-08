import pytest
from myapp import create_app, db

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

# Test app initialization

def test_app_initialization(app):
    assert app is not None

# Test database models

def test_user_model():
    user = User(username='testuser')
    assert user.username == 'testuser'

# Test API endpoints

def test_get_users(client):
    response = client.get('/api/users')
    assert response.status_code == 200

# Test PDF processing

def test_pdf_processing():
    result = process_pdf('sample.pdf')
    assert result is not None

# Test authentication

def test_user_authentication(client):
    response = client.post('/api/login', json={'username': 'testuser', 'password': 'password'})
    assert response.status_code == 200

# Test error handling

def test_error_handling(client):
    response = client.get('/api/notfound')
    assert response.status_code == 404

# Test integration tests

def test_integration(client):
    response = client.post('/api/users', json={'username': 'newuser'})
    assert response.status_code == 201
    response = client.get('/api/users/newuser')
    assert response.json['username'] == 'newuser'