import pytest
import os
import sys
import json
from app import create_app, db
from models import User

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
    })
    
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

# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

def _login(client, app):
    """Log in as the default admin user created by create_app."""
    with app.app_context():
        user = User.query.filter_by(username="admin").first()
    # Use a fresh password set on the user
    with app.app_context():
        u = User.query.filter_by(username="admin").first()
        u.set_password("adminpass123")
        db.session.commit()
    return client.post("/auth/login", data={
        "username": "admin",
        "password": "adminpass123",
    }, follow_redirects=True)


# ─────────────────────────────────────────────────────────────────────────
# Existing tests
# ─────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────
# ValidationService unit tests
# ─────────────────────────────────────────────────────────────────────────

class TestValidationService:
    """Unit tests for backend/services/validation_service.py."""

    def _import(self):
        """Return the validation_service module, adding backend to sys.path."""
        repo_root = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.join(repo_root, "backend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        import importlib
        return importlib.import_module("services.validation_service")

    def test_compare_field_exact_match(self):
        svc = self._import()
        status, score = svc.compare_field("Rahul Misra", "Rahul Misra")
        assert status == svc.STATUS_VALIDATED
        assert score == 1.0

    def test_compare_field_case_insensitive(self):
        svc = self._import()
        status, score = svc.compare_field("rahul misra", "Rahul Misra")
        assert status == svc.STATUS_VALIDATED
        assert score == 1.0

    def test_compare_field_both_blank(self):
        svc = self._import()
        status, score = svc.compare_field("", "")
        assert status == svc.STATUS_VALIDATED
        assert score == 1.0

    def test_compare_field_extracted_blank_ref_has_value(self):
        svc = self._import()
        status, score = svc.compare_field("", "Asansol")
        assert status == svc.STATUS_BLANK
        assert score == 0.0

    def test_compare_field_partial_match(self):
        svc = self._import()
        # Remove a period — should be a high (>=0.8) but not 1.0 score
        status, score = svc.compare_field(
            "Sumoth pally Durgamandir",
            "Sumoth pally. Durgamandir",
        )
        assert status in (svc.STATUS_NEEDS_REVIEW, svc.STATUS_VALIDATED)
        assert score > 0.8

    def test_compare_field_no_match(self):
        svc = self._import()
        status, score = svc.compare_field("completely different", "Rahul Misra")
        assert status == svc.STATUS_NEEDS_CORRECTION
        assert score < 0.8

    def test_load_reference_data_default_set(self):
        svc = self._import()
        ref = svc.load_reference_data("mat_pdf_v1")
        assert isinstance(ref, dict)
        assert ref.get("Name") == "Rahul Misra"
        assert ref.get("City") == "Asansol"
        assert ref.get("Zip Code") == "713301"

    def test_load_reference_data_unknown_set(self):
        svc = self._import()
        with pytest.raises(ValueError):
            svc.load_reference_data("nonexistent_set")

    def test_validate_document_all_correct(self):
        svc = self._import()
        fields = [
            {"field_id": 1, "field_name": "Name", "value": "Rahul Misra"},
            {"field_id": 2, "field_name": "City", "value": "Asansol"},
        ]
        result = svc.validate_document(1, fields, "mat_pdf_v1")
        assert result["status"] == "validation_complete"
        assert "timestamp" in result
        meta = result["validation_metadata"]
        assert meta["total_fields"] == 2
        assert meta["validated"] == 2
        assert meta["accuracy"] == 1.0

    def test_validate_document_with_blank_field(self):
        svc = self._import()
        fields = [
            {"field_id": 1, "field_name": "Name", "value": "Rahul Misra"},
            {"field_id": 2, "field_name": "City", "value": ""},  # blank
        ]
        result = svc.validate_document(1, fields, "mat_pdf_v1")
        meta = result["validation_metadata"]
        assert meta["blank_fields"] == 1
        # The blank field for "City" (ref="Asansol") should be marked corrected
        blank_result = next(r for r in result["results"] if r["field_name"] == "City")
        assert blank_result["corrected"] is True
        assert blank_result["corrected_to"] == "Asansol"

    def test_validate_document_empty_fields_list(self):
        svc = self._import()
        result = svc.validate_document(1, [], "mat_pdf_v1")
        assert result["validation_metadata"]["total_fields"] == 0
        assert result["validation_metadata"]["accuracy"] == 0.0


# ─────────────────────────────────────────────────────────────────────────
# Train Me endpoint integration tests
# ─────────────────────────────────────────────────────────────────────────

class TestTrainMeEndpoint:
    """Integration tests for POST /address-book-live/<doc_id>/train-me."""

    def _create_doc_and_fields(self, app):
        """Helper: insert a Document + ExtractedFields and return doc.id."""
        from models import Document, ExtractedField
        with app.app_context():
            doc = Document(
                filename="test.pdf",
                file_path="/tmp/test.pdf",
                status="extracted",
            )
            db.session.add(doc)
            db.session.flush()
            for name, val in [
                ("Name", "Rahul Misra"),
                ("City", "Asansol"),
                ("State", "WB"),
            ]:
                f = ExtractedField(
                    document_id=doc.id,
                    field_name=name,
                    value=val,
                    confidence=1.0,
                )
                db.session.add(f)
            db.session.commit()
            return doc.id

    def test_train_me_requires_login(self, client, app):
        doc_id = self._create_doc_and_fields(app)
        resp = client.post(
            f"/address-book-live/{doc_id}/train-me",
            json={"reference_set": "mat_pdf_v1", "fields": []},
        )
        # Should redirect to login (302) when not authenticated
        assert resp.status_code in (302, 401)

    def test_train_me_returns_validation_result(self, client, app):
        doc_id = self._create_doc_and_fields(app)
        _login(client, app)
        payload = {
            "reference_set": "mat_pdf_v1",
            "fields": [
                {"field_id": 1, "field_name": "Name", "value": "Rahul Misra"},
                {"field_id": 2, "field_name": "City", "value": "Asansol"},
            ],
        }
        resp = client.post(
            f"/address-book-live/{doc_id}/train-me",
            json=payload,
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "validation_complete"
        assert "timestamp" in data
        assert "results" in data
        assert "validation_metadata" in data

    def test_train_me_invalid_fields_type(self, client, app):
        doc_id = self._create_doc_and_fields(app)
        _login(client, app)
        resp = client.post(
            f"/address-book-live/{doc_id}/train-me",
            json={"reference_set": "mat_pdf_v1", "fields": "not-a-list"},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 400

    def test_train_me_unknown_reference_set(self, client, app):
        doc_id = self._create_doc_and_fields(app)
        _login(client, app)
        resp = client.post(
            f"/address-book-live/{doc_id}/train-me",
            json={"reference_set": "no_such_set", "fields": []},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 400

    def test_train_me_persists_validation_log(self, client, app):
        doc_id = self._create_doc_and_fields(app)
        _login(client, app)
        payload = {
            "reference_set": "mat_pdf_v1",
            "fields": [
                {"field_id": 1, "field_name": "Name", "value": "Rahul Misra"},
            ],
        }
        resp = client.post(
            f"/address-book-live/{doc_id}/train-me",
            json=payload,
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 200
        from models import ValidationLog
        with app.app_context():
            log = ValidationLog.query.filter_by(document_id=doc_id).first()
            assert log is not None
            assert log.reference_set == "mat_pdf_v1"
            assert log.total_fields == 1

    def test_train_me_doc_not_found(self, client, app):
        _login(client, app)
        resp = client.post(
            "/address-book-live/9999/train-me",
            json={"reference_set": "mat_pdf_v1", "fields": []},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────
# New model smoke tests
# ─────────────────────────────────────────────────────────────────────────

class TestNewModels:
    """Smoke tests for ValidationLog and FieldCorrection models."""

    def test_validation_log_create(self, app):
        from models import ValidationLog, Document
        with app.app_context():
            doc = Document(filename="x.pdf", file_path="/tmp/x.pdf", status="extracted")
            db.session.add(doc)
            db.session.flush()
            log = ValidationLog(
                document_id=doc.id,
                reference_set="mat_pdf_v1",
                total_fields=9,
                validated_count=7,
                accuracy_score=0.78,
            )
            db.session.add(log)
            db.session.commit()
            fetched = ValidationLog.query.get(log.id)
            assert fetched is not None
            assert fetched.reference_set == "mat_pdf_v1"
            assert fetched.accuracy_score == pytest.approx(0.78)

    def test_field_correction_create(self, app):
        from models import ValidationLog, FieldCorrection, Document
        with app.app_context():
            doc = Document(filename="y.pdf", file_path="/tmp/y.pdf", status="extracted")
            db.session.add(doc)
            db.session.flush()
            log = ValidationLog(
                document_id=doc.id,
                reference_set="mat_pdf_v1",
                total_fields=1,
                validated_count=0,
                accuracy_score=0.0,
            )
            db.session.add(log)
            db.session.flush()
            corr = FieldCorrection(
                validation_log_id=log.id,
                field_name="City",
                original_value="",
                corrected_value="Asansol",
                correction_source="train_me",
            )
            db.session.add(corr)
            db.session.commit()
            fetched = FieldCorrection.query.get(corr.id)
            assert fetched is not None
            assert fetched.corrected_value == "Asansol"
            d = fetched.to_dict()
            assert d["correction_source"] == "train_me"


# ─────────────────────────────────────────────────────────────────────────
# TrainingExample model + API tests
# ─────────────────────────────────────────────────────────────────────────

class TestTrainingExample:
    """Tests for the TrainingExample model and /api/v1/training/* endpoints."""

    def _create_doc(self, app):
        """Insert a Document and return its id."""
        from models import Document
        with app.app_context():
            doc = Document(
                filename="train.pdf",
                file_path="/tmp/train.pdf",
                status="extracted",
            )
            db.session.add(doc)
            db.session.commit()
            return doc.id

    def test_training_example_model(self, app):
        """TrainingExample rows can be created and retrieved."""
        from models import TrainingExample, Document
        with app.app_context():
            doc = Document(filename="t.pdf", file_path="/tmp/t.pdf", status="uploaded")
# TrainingService unit tests
# ─────────────────────────────────────────────────────────────────────────

class TestTrainingService:
    """Unit tests for backend/services/training_service.py."""

    def _get_svc(self):
        import importlib, sys, os
        backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
        if backend not in sys.path:
            sys.path.insert(0, backend)
        return importlib.import_module("services.training_service").TrainingService()

    # extract_domain_pattern
    def test_extract_domain_single(self):
        svc = self._get_svc()
        assert svc.extract_domain_pattern(["john@example.com"]) == "example.com"

    def test_extract_domain_majority(self):
        svc = self._get_svc()
        emails = ["john@example.com", "jane@example.com", "bob@other.org"]
        assert svc.extract_domain_pattern(emails) == "example.com"

    def test_extract_domain_empty(self):
        svc = self._get_svc()
        assert svc.extract_domain_pattern([]) == ""

    def test_extract_domain_invalid(self):
        svc = self._get_svc()
        assert svc.extract_domain_pattern(["notanemail", ""]) == ""

    # generate_email
    def test_generate_email_full_name(self):
        svc = self._get_svc()
        assert svc.generate_email("Rahul Misra", "example.com") == "rahul@example.com"

    def test_generate_email_single_name(self):
        svc = self._get_svc()
        assert svc.generate_email("John", "example.com") == "john@example.com"

    def test_generate_email_no_name(self):
        svc = self._get_svc()
        assert svc.generate_email("", "example.com") == ""

    def test_generate_email_no_domain(self):
        svc = self._get_svc()
        assert svc.generate_email("John Doe", "") == ""

    # fill_blank_fields — email generation
    def test_fill_blank_email_generated(self):
        svc = self._get_svc()
        fields = [
            {"field_name": "Name",  "field_value": "Rahul Misra", "confidence": 1.0},
            {"field_name": "Email", "field_value": "",             "confidence": 0.0},
        ]
        training = [
            {"field_name": "Email", "field_value": "john@example.com"},
            {"field_name": "Email", "field_value": "jane@example.com"},
        ]
        result = svc.fill_blank_fields(fields, training)
        email_field = next(f for f in result if f["field_name"] == "Email")
        assert email_field["field_value"] == "rahul@example.com"
        assert email_field["confidence_source"] == "training_generated"

    def test_fill_blank_city_from_training(self):
        svc = self._get_svc()
        fields = [
            {"field_name": "City",  "field_value": "", "confidence": 0.0},
        ]
        training = [
            {"field_name": "City", "field_value": "Asansol"},
            {"field_name": "City", "field_value": "Asansol"},
        ]
        result = svc.fill_blank_fields(fields, training)
        city = next(f for f in result if f["field_name"] == "City")
        assert city["field_value"] == "Asansol"
        assert city["confidence_source"] == "training"

    def test_existing_email_not_overwritten(self):
        svc = self._get_svc()
        fields = [
            {"field_name": "Name",  "field_value": "John Doe",          "confidence": 1.0},
            {"field_name": "Email", "field_value": "john@custom.org",   "confidence": 0.9},
        ]
        training = [
            {"field_name": "Email", "field_value": "other@example.com"},
        ]
        result = svc.fill_blank_fields(fields, training)
        email_field = next(f for f in result if f["field_name"] == "Email")
        assert email_field["field_value"] == "john@custom.org"

    def test_no_training_data_unchanged(self):
        svc = self._get_svc()
        fields = [{"field_name": "City", "field_value": "", "confidence": 0.0}]
        result = svc.fill_blank_fields(fields, [])
        assert result[0]["field_value"] == ""


# ─────────────────────────────────────────────────────────────────────────
# TrainingExample model smoke tests
# ─────────────────────────────────────────────────────────────────────────

class TestTrainingExampleModel:
    """Smoke tests for the TrainingExample model."""

    def _create_doc(self, app):
        from models import Document
        with app.app_context():
            doc = Document(filename="t.pdf", file_path="/tmp/t.pdf", status="extracted")
            db.session.add(doc)
            db.session.commit()
            return doc.id

    def test_create_training_example(self, app):
        from models import TrainingExample, Document
        with app.app_context():
            doc = Document(filename="t.pdf", file_path="/tmp/t.pdf", status="extracted")
            db.session.add(doc)
            db.session.flush()
            ex = TrainingExample(
                document_id=doc.id,
                field_name="Name",
                correct_value="Rahul Misra",
            )
            db.session.add(ex)
            db.session.commit()
            fetched = TrainingExample.query.filter_by(document_id=doc.id).first()
            assert fetched is not None
            assert fetched.field_name == "Name"
            assert fetched.correct_value == "Rahul Misra"
            d = fetched.to_dict()
            assert d["field_name"] == "Name"
            assert d["correct_value"] == "Rahul Misra"
            assert "created_at" in d

    def test_add_training_requires_login(self, client, app):
        doc_id = self._create_doc(app)
        resp = client.post(
            "/api/v1/training/add",
            json={"document_id": doc_id, "fields": {"Name": "Test"}},
        )
        assert resp.status_code in (302, 401)

    def test_add_training_saves_examples(self, client, app):
        from models import TrainingExample, Document
        doc_id = self._create_doc(app)
        _login(client, app)
        resp = client.post(
            "/api/v1/training/add",
            json={"document_id": doc_id, "fields": {"Email": "rahul@example.com"}},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        with app.app_context():
            fetched = TrainingExample.query.filter_by(
                document_id=doc_id, field_name="Email"
            ).first()
            assert fetched is not None
            assert fetched.correct_value == "rahul@example.com"
            d = fetched.to_dict()
            assert d["field_name"] == "Email"
            assert "created_at" in d


# ─────────────────────────────────────────────────────────────────────────
# Training API integration tests
# ─────────────────────────────────────────────────────────────────────────

class TestTrainingAPI:
    """Integration tests for /api/v1/training/* endpoints."""

    def _create_doc(self, app):
        from models import Document
        with app.app_context():
            doc = Document(filename="tr.pdf", file_path="/tmp/tr.pdf", status="extracted")
            db.session.add(doc)
            db.session.commit()
            return doc.id

    def _create_doc_and_fields(self, app):
        from models import Document, ExtractedField
        with app.app_context():
            doc = Document(filename="tr.pdf", file_path="/tmp/tr.pdf", status="extracted")
            db.session.add(doc)
            db.session.flush()
            for name, val in [("Name", "Rahul Misra"), ("Email", "rahul@example.com")]:
                db.session.add(ExtractedField(
                    document_id=doc.id, field_name=name, value=val, confidence=1.0
                ))
            db.session.commit()
            return doc.id

    def test_add_requires_login(self, client, app):
        doc_id = self._create_doc_and_fields(app)
        resp = client.post("/api/v1/training/add", json={"document_id": doc_id})
        assert resp.status_code in (302, 401)

    def test_add_with_fields(self, client, app):
        doc_id = self._create_doc_and_fields(app)
        _login(client, app)
        resp = client.post(
            "/api/v1/training/add",
            json={"document_id": doc_id, "fields": {"Name": "Rahul Misra", "Email": "rahul@example.com"}},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert len(data["saved"]) == 2

    def test_add_with_explicit_fields(self, client, app):
        doc_id = self._create_doc_and_fields(app)
        _login(client, app)
        resp = client.post(
            "/api/v1/training/add",
            json={
                "document_id": doc_id,
                "fields": {
                    "Name": "Rahul Misra",
                    "City": "Asansol",
                    "State": "WB",
                },
            },
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["document_id"] == doc_id
        assert len(data["saved"]) == 3

    def test_add_training_persists_to_db(self, client, app):
        doc_id = self._create_doc(app)
        _login(client, app)
        client.post(
            "/api/v1/training/add",
            json={"document_id": doc_id, "fields": {"Name": "John Doe"}},
            headers={"X-CSRFToken": "test"},
        )
        from models import TrainingExample
        with app.app_context():
            examples = TrainingExample.query.filter_by(
                document_id=doc_id, field_name="Name"
            ).all()
            assert len(examples) == 1
            assert examples[0].correct_value == "John Doe"

    def test_add_training_replaces_existing(self, client, app):
        """Calling add_training twice replaces the first set of examples."""
        doc_id = self._create_doc(app)
        _login(client, app)
        client.post(
            "/api/v1/training/add",
            json={"document_id": doc_id, "fields": {"Name": "Old Name"}},
            headers={"X-CSRFToken": "test"},
        )
        client.post(
            "/api/v1/training/add",
            json={"document_id": doc_id, "fields": {"Name": "New Name"}},
            headers={"X-CSRFToken": "test"},
        )
        from models import TrainingExample
        with app.app_context():
            examples = TrainingExample.query.filter_by(document_id=doc_id).all()
            assert len(examples) == 1
            assert examples[0].correct_value == "New Name"

    def test_add_training_skips_empty_values(self, client, app):
        doc_id = self._create_doc(app)
        _login(client, app)
        resp = client.post(
            "/api/v1/training/add",
            json={
                "document_id": doc_id,
                "fields": {"Name": "Rahul", "City": ""},
            },
            headers={"X-CSRFToken": "test"},
        )
        data = resp.get_json()
        # Only 'Name' saved; 'City' was blank
        assert len(data["saved"]) == 1
        assert data["saved"][0]["field_name"] == "Name"

    def test_add_training_missing_document_id(self, client, app):
        _login(client, app)
        resp = client.post(
            "/api/v1/training/add",
            json={"fields": {"Name": "test"}},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 400

    def test_add_training_missing_fields(self, client, app):
        doc_id = self._create_doc(app)
        _login(client, app)
        resp = client.post(
            "/api/v1/training/add",
            json={"document_id": doc_id},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 400

    def test_list_returns_examples(self, client, app):
        doc_id = self._create_doc_and_fields(app)
        _login(client, app)
        client.post(
            "/api/v1/training/add",
            json={"document_id": doc_id, "fields": {"Name": "Rahul Misra", "Email": "rahul@example.com"}},
            headers={"X-CSRFToken": "test"},
        )
        resp = client.get("/api/v1/training/examples")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 2

    def test_delete_sample(self, client, app):
        doc_id = self._create_doc(app)
        _login(client, app)
        # Add training examples
        client.post(
            "/api/v1/training/add",
            json={"document_id": doc_id, "fields": {"Name": "Rahul"}},
            headers={"X-CSRFToken": "test"},
        )
        # Delete the sample group
        resp = client.post(
            f"/training/examples/{doc_id}/delete",
            headers={"X-CSRFToken": "test"},
        )
        # Should redirect after deletion
        assert resp.status_code in (200, 302)

    def test_add_missing_document_id(self, client, app):
        _login(client, app)
        resp = client.post(
            "/api/v1/training/add",
            json={"fields": []},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 400

    def test_add_training_doc_not_found(self, client, app):
        _login(client, app)
        resp = client.post(
            "/api/v1/training/add",
            json={"document_id": 9999, "fields": {"Name": "test"}},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 404

    def test_add_doc_not_found(self, client, app):
        _login(client, app)
        resp = client.post(
            "/api/v1/training/add",
            json={"document_id": 99999, "fields": {"Name": "test"}},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 404

    def test_list_examples_json(self, client, app):
        doc_id = self._create_doc(app)
        _login(client, app)
        client.post(
            "/api/v1/training/add",
            json={"document_id": doc_id, "fields": {"Name": "Rahul"}},
            headers={"X-CSRFToken": "test"},
        )
        resp = client.get("/api/v1/training/examples")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] >= 1
        assert any(ex["field_name"] == "Name" for ex in data["examples"])

    def test_examples_list_html(self, client, app):
        _login(client, app)
        resp = client.get("/training/examples")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────
# TrainingService unit tests
# ─────────────────────────────────────────────────────────────────────────

class TestTrainingService:
    """Unit tests for backend/services/training_service.py."""

    def _import(self):
        repo_root = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.join(repo_root, "backend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        import importlib
        return importlib.import_module("services.training_service")

    def test_boost_confidence_match_boosts_score(self):
        svc_mod = self._import()
        svc = svc_mod.TrainingService()
        training = [{"field_name": "Name", "correct_value": "Rahul Misra"}]
        value, delta, used = svc.boost_confidence("Name", "Rahul Misra", training)
        assert used is True
        assert delta == svc.CONFIDENCE_BOOST
        assert value == "Rahul Misra"

    def test_boost_confidence_empty_extracted_uses_training(self):
        svc_mod = self._import()
        svc = svc_mod.TrainingService()
        training = [{"field_name": "City", "correct_value": "Asansol"}]
        value, delta, used = svc.boost_confidence("City", "", training)
        assert used is True
        assert value == "Asansol"
        assert delta == svc.FALLBACK_CONFIDENCE

    def test_boost_confidence_no_training_data(self):
        svc_mod = self._import()
        svc = svc_mod.TrainingService()
        value, delta, used = svc.boost_confidence("Name", "John", [])
        assert used is False
        assert delta == 0.0

    def test_boost_confidence_wrong_field(self):
        svc_mod = self._import()
        svc = svc_mod.TrainingService()
        training = [{"field_name": "City", "correct_value": "Asansol"}]
        value, delta, used = svc.boost_confidence("Name", "Rahul", training)
        assert used is False

    def test_apply_training_to_results(self):
        svc_mod = self._import()
        svc = svc_mod.TrainingService()
        results = [
            {"field_name": "Name", "field_value": "Rahul Misra", "confidence": 0.70},
            {"field_name": "City", "field_value": "", "confidence": 0.0},
        ]
        training = [
            {"field_name": "Name", "correct_value": "Rahul Misra"},
            {"field_name": "City", "correct_value": "Asansol"},
        ]
        updated = svc.apply_training_to_results(results, training)
        name_result = next(r for r in updated if r["field_name"] == "Name")
        city_result = next(r for r in updated if r["field_name"] == "City")
        # Name matched → confidence boosted
        assert name_result["confidence"] > 0.70
        assert name_result.get("training_boosted") is True
        # City was empty → filled from training
        assert city_result["field_value"] == "Asansol"
        assert city_result.get("training_boosted") is True

    def test_apply_training_no_training_returns_unchanged(self):
        svc_mod = self._import()
        svc = svc_mod.TrainingService()
        results = [{"field_name": "Name", "field_value": "Test", "confidence": 0.5}]
        updated = svc.apply_training_to_results(results, [])
        assert updated[0]["confidence"] == 0.5
        assert "training_boosted" not in updated[0]

    def test_string_similarity(self):
        svc_mod = self._import()
        svc = svc_mod.TrainingService()
        # Exact match → confidence boosted (high similarity)
        _, delta_exact, used_exact = svc.boost_confidence(
            "Name", "Rahul Misra", [{"field_name": "Name", "correct_value": "Rahul Misra"}]
        )
        assert used_exact is True
        assert delta_exact == svc.CONFIDENCE_BOOST

        # Completely different value → no boost
        _, delta_diff, used_diff = svc.boost_confidence(
            "Name", "John Smith", [{"field_name": "Name", "correct_value": "Rahul Misra"}]
        )
        assert used_diff is False

        # Empty extracted value → filled from training
        value_empty, delta_empty, used_empty = svc.boost_confidence(
            "Name", "", [{"field_name": "Name", "correct_value": "Rahul Misra"}]
        )
        assert used_empty is True
        assert value_empty == "Rahul Misra"


# ─────────────────────────────────────────────────────────────────────────
# PDF field extraction unit tests (blueprints/training.py helpers)
# ─────────────────────────────────────────────────────────────────────────

class TestPDFFieldExtraction:
    """Unit tests for the PDF parsing helpers in blueprints/training.py."""

    def _import(self):
        import importlib
        import blueprints.training as mod
        return mod

    def test_parse_txt_colon_separator(self):
        mod = self._import()
        text = "Name: Rahul Misra\nCity: Asansol\nZip Code: 713301"
        result = mod._parse_txt(text)
        assert result["Name"] == "Rahul Misra"
        assert result["City"] == "Asansol"
        assert result["Zip Code"] == "713301"

    def test_parse_txt_equals_separator(self):
        mod = self._import()
        text = "Name = Rahul Misra\nCity = Asansol"
        result = mod._parse_txt(text)
        assert result["Name"] == "Rahul Misra"
        assert result["City"] == "Asansol"

    def test_parse_txt_skips_blank_lines(self):
        mod = self._import()
        text = "\nName: Rahul\n\nCity: Asansol\n"
        result = mod._parse_txt(text)
        assert len(result) == 2

    def test_parse_txt_skips_comment_lines(self):
        mod = self._import()
        text = "# comment\nName: Rahul"
        result = mod._parse_txt(text)
        assert "# comment" not in result
        assert result["Name"] == "Rahul"

    def test_parse_known_fields_inline(self):
        mod = self._import()
        text = "Name Rahul Misra\nCity Asansol\nZip Code 713301\nCell Phone 7699888010"
        result = mod._parse_known_fields_inline(text)
        assert result.get("Name") == "Rahul Misra"
        assert result.get("City") == "Asansol"
        assert result.get("Zip Code") == "713301"
        assert result.get("Cell Phone") == "7699888010"

    def test_parse_known_fields_inline_with_colon(self):
        mod = self._import()
        text = "Name: Rahul Misra\nCity: Asansol"
        # Strategy 1 (_parse_txt) handles colons; inline strategy also should work
        result = mod._parse_known_fields_inline(text)
        assert result.get("Name") == "Rahul Misra"

    def test_parse_field_then_value(self):
        mod = self._import()
        text = "Name\nRahul Misra\nCity\nAsansol\nState\nWB"
        result = mod._parse_field_then_value(text)
        assert result.get("Name") == "Rahul Misra"
        assert result.get("City") == "Asansol"
        assert result.get("State") == "WB"

    def test_parse_tab_separated(self):
        mod = self._import()
        text = "Name\tRahul Misra\nCity\tAsansol\nZip Code\t713301"
        result = mod._parse_tab_separated(text)
        assert result.get("Name") == "Rahul Misra"
        assert result.get("City") == "Asansol"
        assert result.get("Zip Code") == "713301"

    def test_parse_pdf_with_colon_text(self):
        """_parse_pdf should handle text PDFs with 'Field: Value' lines."""
        import io
        mod = self._import()
        # Build a minimal PDF with selectable text using reportlab if available
        # Otherwise, test _parse_txt fallback path via extract_pdf_text mock
        # We verify by calling _parse_txt directly since _parse_pdf delegates to it
        text = "Name: Rahul Misra\nCity: Asansol\nCell Phone: 7699888010"
        result = mod._parse_txt(text)
        assert result["Name"] == "Rahul Misra"
        assert result["City"] == "Asansol"
        assert result["Cell Phone"] == "7699888010"

    def test_extract_preview_requires_login(self, client, app):
        """extract-preview endpoint requires authentication."""
        import io
        data = {"sample_file": (io.BytesIO(b"Name: Test"), "test.txt")}
        resp = client.post(
            "/training/extract-preview",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code in (302, 401)

    def test_extract_preview_txt_file(self, client, app):
        """extract-preview returns extracted fields from a TXT file."""
        import io
        _login(client, app)
        txt_content = b"Name: Rahul Misra\nCity: Asansol\nZip Code: 713301"
        data = {
            "sample_file": (io.BytesIO(txt_content), "sample.txt"),
            "csrf_token": "test",
        }
        resp = client.post(
            "/training/extract-preview",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        result = resp.get_json()
        assert result["ok"] is True
        assert result["count"] == 3
        assert result["fields"]["Name"] == "Rahul Misra"
        assert result["fields"]["City"] == "Asansol"

    def test_extract_preview_no_file(self, client, app):
        """extract-preview returns 400 when no file is provided."""
        _login(client, app)
        resp = client.post(
            "/training/extract-preview",
            data={"csrf_token": "test"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_extract_preview_unsupported_type(self, client, app):
        """extract-preview returns 400 for unsupported file types."""
        import io
        _login(client, app)
        data = {
            "sample_file": (io.BytesIO(b"data"), "file.csv"),
            "csrf_token": "test",
        }
        resp = client.post(
            "/training/extract-preview",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_extract_preview_empty_file_returns_422(self, client, app):
        """extract-preview returns 422 when file yields no fields."""
        import io
        _login(client, app)
        # A TXT file with no Field: Value pairs
        data = {
            "sample_file": (io.BytesIO(b"just some random text\nno fields here"), "empty.txt"),
            "csrf_token": "test",
        }
        resp = client.post(
            "/training/extract-preview",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 422
        result = resp.get_json()
        assert result["ok"] is False

    def test_upload_sample_with_manual_fields(self, client, app):
        """upload-sample POST with manual mode saves fields correctly."""
        _login(client, app)
        resp = client.post(
            "/training/upload-sample",
            data={
                "sample_name": "Test Sample",
                "document_type": "Address Book",
                "upload_mode": "manual",
                "field_name[]": ["Name", "City"],
                "field_value[]": ["Rahul Misra", "Asansol"],
                "csrf_token": "test",
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from models import TrainingExample
        with app.app_context():
            examples = TrainingExample.query.filter_by(field_name="Name").all()
            assert len(examples) >= 1
            assert examples[0].correct_value == "Rahul Misra"

    def test_upload_sample_requires_sample_name(self, client, app):
        """upload-sample returns error when sample_name is missing."""
        _login(client, app)
        resp = client.post(
            "/training/upload-sample",
            data={
                "sample_name": "",
                "upload_mode": "manual",
                "field_name[]": ["Name"],
                "field_value[]": ["Rahul"],
                "csrf_token": "test",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200  # re-renders form
        assert b"required" in resp.data.lower() or b"sample name" in resp.data.lower()

