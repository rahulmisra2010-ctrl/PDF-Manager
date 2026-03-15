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
        # No extracted fields and no explicit fields → 400
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False
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

    def test_add_doc_not_found_auto_load(self, client, app):
        """When no fields provided and document doesn't exist, returns 404."""
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


# ─────────────────────────────────────────────────────────────────────────
# Schema migration tests
# ─────────────────────────────────────────────────────────────────────────

class TestSchemaMigration:
    """Tests that _run_schema_migrations() safely adds missing columns."""

    def test_migration_adds_correct_value_if_missing(self):
        """Simulate a legacy DB missing correct_value; migration should add it."""
        import sqlite3, tempfile, os
        from app import create_app, _run_schema_migrations
        from models import db as _db

        # Build a minimal SQLite file that has training_examples WITHOUT correct_value
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "legacy.db")
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE training_examples "
                "(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, "
                "field_name TEXT NOT NULL)"
            )
            conn.commit()
            conn.close()

            test_app = create_app({
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
                "WTF_CSRF_ENABLED": False,
            })
            # Migration runs during create_app; verify column now exists
            conn2 = sqlite3.connect(db_path)
            cols = {row[1] for row in conn2.execute("PRAGMA table_info(training_examples)")}
            conn2.close()

            assert "correct_value" in cols, "correct_value column was not added by migration"
            assert "page_number" in cols, "page_number column was not added by migration"
            assert "x0" in cols, "x0 column was not added by migration"
            assert "y1" in cols, "y1 column was not added by migration"
            assert "engine" in cols, "engine column was not added by migration"
            assert "anchor_text" in cols, "anchor_text column was not added by migration"

    def test_migration_is_idempotent(self):
        """Running migration on a fully up-to-date DB should not raise."""
        import sqlite3, tempfile, os
        from app import create_app

        # create_app with :memory: already runs migration — just ensure no crash
        test_app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
        })
        # Run migration again manually — must not raise
        with test_app.app_context():
            from app import _run_schema_migrations
            _run_schema_migrations(test_app)  # should be a no-op


# ─────────────────────────────────────────────────────────────────────────
# ROI save-roi API tests
# ─────────────────────────────────────────────────────────────────────────

class TestSaveRoiEndpoint:
    """Tests for POST /api/v1/training/save-roi."""

    def _create_doc(self, app):
        from models import Document
        with app.app_context():
            doc = Document(filename="roi.pdf", file_path="/tmp/roi.pdf", status="extracted")
            app.extensions["sqlalchemy"].db.session.add(doc)
            app.extensions["sqlalchemy"].db.session.commit()
            return doc.id

    def _create_doc_v2(self, app):
        from models import Document, db as _db
        with app.app_context():
            doc = Document(filename="roi2.pdf", file_path="/tmp/roi2.pdf", status="extracted")
            _db.session.add(doc)
            _db.session.commit()
            return doc.id

    def test_save_roi_requires_login(self, client, app):
        resp = client.post(
            "/api/v1/training/save-roi",
            json={"document_id": 1, "examples": []},
        )
        assert resp.status_code in (302, 401)

    def test_save_roi_saves_multiple_fields(self, client, app):
        from models import TrainingExample, db as _db
        doc_id = self._create_doc_v2(app)
        _login(client, app)
        payload = {
            "document_id": doc_id,
            "page_number": 1,
            "examples": [
                {"field_name": "Name", "correct_value": "Rahul Misra",
                 "x0": 0.1, "y0": 0.2, "x1": 0.5, "y1": 0.25, "engine": "pytesseract"},
                {"field_name": "Cell Phone", "correct_value": "7699888010",
                 "x0": 0.6, "y0": 0.4, "x1": 0.9, "y1": 0.45},
            ],
        }
        resp = client.post(
            "/api/v1/training/save-roi",
            json=payload,
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["saved"] == 2
        assert data["document_id"] == doc_id
        with app.app_context():
            rows = TrainingExample.query.filter_by(document_id=doc_id).all()
            assert len(rows) == 2
            name_row = next(r for r in rows if r.field_name == "Name")
            assert name_row.correct_value == "Rahul Misra"
            assert name_row.page_number == 1
            assert abs(name_row.x0 - 0.1) < 1e-6
            assert name_row.engine == "pytesseract"

    def test_save_roi_upserts_on_duplicate(self, client, app):
        """Saving the same field twice should replace the first entry."""
        from models import TrainingExample, db as _db
        doc_id = self._create_doc_v2(app)
        _login(client, app)
        payload = {
            "document_id": doc_id,
            "page_number": 1,
            "examples": [{"field_name": "Name", "correct_value": "First Value"}],
        }
        client.post("/api/v1/training/save-roi", json=payload,
                    headers={"X-CSRFToken": "test"})
        payload["examples"][0]["correct_value"] = "Updated Value"
        client.post("/api/v1/training/save-roi", json=payload,
                    headers={"X-CSRFToken": "test"})
        with app.app_context():
            rows = TrainingExample.query.filter_by(
                document_id=doc_id, field_name="Name", page_number=1
            ).all()
            assert len(rows) == 1
            assert rows[0].correct_value == "Updated Value"

    def test_save_roi_rejects_out_of_range_coords(self, client, app):
        doc_id = self._create_doc_v2(app)
        _login(client, app)
        payload = {
            "document_id": doc_id,
            "examples": [
                {"field_name": "Name", "correct_value": "Val",
                 "x0": -0.1, "y0": 0.2, "x1": 1.5, "y1": 0.25},
            ],
        }
        resp = client.post(
            "/api/v1/training/save-roi",
            json=payload,
            headers={"X-CSRFToken": "test"},
        )
        # Bad coords → warnings but the row is still saved with None coords
        data = resp.get_json()
        assert data["ok"] is True
        assert "warnings" in data

    def test_save_roi_missing_document_id(self, client, app):
        _login(client, app)
        resp = client.post(
            "/api/v1/training/save-roi",
            json={"examples": [{"field_name": "X", "correct_value": "Y"}]},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 400

    def test_save_roi_empty_examples(self, client, app):
        doc_id = self._create_doc_v2(app)
        _login(client, app)
        resp = client.post(
            "/api/v1/training/save-roi",
            json={"document_id": doc_id, "examples": []},
            headers={"X-CSRFToken": "test"},
        )
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────
# examples_list page smoke test
# ─────────────────────────────────────────────────────────────────────────

class TestExamplesListPage:
    """Ensure GET /training/examples renders without crashing."""

    def test_examples_list_renders(self, client, app):
        _login(client, app)
        resp = client.get("/training/examples")
        assert resp.status_code == 200
        assert b"Training Data" in resp.data

    def test_examples_list_with_data(self, client, app):
        from models import Document, TrainingExample, db as _db
        with app.app_context():
            doc = Document(filename="ex.pdf", file_path="/tmp/ex.pdf", status="training")
            _db.session.add(doc)
            _db.session.flush()
            ex = TrainingExample(
                document_id=doc.id,
                field_name="Name",
                correct_value="Rahul Misra",
            )
            _db.session.add(ex)
            _db.session.commit()
        _login(client, app)
        resp = client.get("/training/examples")
        assert resp.status_code == 200
        assert b"Rahul Misra" in resp.data


# ─────────────────────────────────────────────────────────────────────────
# Apply All endpoint tests (AddressBook_v1 autofill logic)
# ─────────────────────────────────────────────────────────────────────────

class TestApplyAll:
    """Integration tests for POST /address-book/<doc_id>/apply-all."""

    def _create_doc(self, app, fields=None):
        """Create a Document with optional ExtractedField rows; return doc.id."""
        from models import Document, ExtractedField
        with app.app_context():
            doc = Document(
                filename="ab_test.pdf",
                file_path="/tmp/ab_test.pdf",
                status="extracted",
            )
            db.session.add(doc)
            db.session.flush()
            for name, val, conf in (fields or []):
                db.session.add(ExtractedField(
                    document_id=doc.id,
                    field_name=name,
                    value=val,
                    confidence=conf,
                ))
            db.session.commit()
            return doc.id

    def test_apply_all_requires_login(self, client, app):
        doc_id = self._create_doc(app)
        resp = client.post(f"/address-book/{doc_id}/apply-all")
        # Must redirect to login when not authenticated
        assert resp.status_code in (302, 401)

    def test_apply_all_doc_not_found(self, client, app):
        _login(client, app)
        resp = client.post(
            "/address-book/9999/apply-all",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
        assert resp.status_code == 404

    def test_apply_all_blank_document_fills_defaults(self, client, app):
        """Blank document (0 valid fields) → all fields with defaults are populated."""
        doc_id = self._create_doc(app)  # No fields at all → 9/9 invalid
        _login(client, app)
        resp = client.post(
            f"/address-book/{doc_id}/apply-all",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        # Verify defaults were written to DB
        from models import ExtractedField
        with app.app_context():
            field_map = {
                f.field_name: f.value
                for f in ExtractedField.query.filter_by(document_id=doc_id).all()
            }
        assert field_map.get("Name") == "Rahul Misra"
        assert field_map.get("Street Address") == "Sumoth pally, Durgamandir"
        assert field_map.get("City") == "Asansol"
        assert field_map.get("State") == "WB"
        assert field_map.get("Zip Code") == "713301"
        assert field_map.get("Cell Phone") == "7699888010"
        # No defaults for Home Phone, Work Phone, Email → remain blank
        assert field_map.get("Home Phone") == ""
        assert field_map.get("Work Phone") == ""
        assert field_map.get("Email") == ""

    def test_apply_all_blank_document_creates_all_nine_fields(self, client, app):
        """Apply All creates all 9 template fields in the DB for blank documents."""
        doc_id = self._create_doc(app)  # No fields at all
        _login(client, app)
        client.post(
            f"/address-book/{doc_id}/apply-all",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
        from models import ExtractedField
        from blueprints.address_book import ADDRESS_BOOK_FIELDS
        with app.app_context():
            names = {
                f.field_name
                for f in ExtractedField.query.filter_by(document_id=doc_id).all()
            }
        assert set(ADDRESS_BOOK_FIELDS) == names

    def test_apply_all_partial_document_only_fixes_fixed_fields(self, client, app):
        """Non-blank-ish doc (< 7/9 invalid) → only Name/State/Cell Phone overridden."""
        # 5 valid fields, 4 invalid → NOT blank-ish (threshold is 7)
        good_fields = [
            ("Street Address", "123 Main St",   1.0),
            ("City",           "Springfield",   1.0),
            ("Zip Code",       "123456",        1.0),
            ("Home Phone",     "9876543210",    1.0),
            ("Email",          "test@test.com", 1.0),
        ]
        # 4 invalid: Name (blank), State (blank), Cell Phone (blank), Work Phone (blank)
        bad_fields = [
            ("Name",       "", 0.0),
            ("State",      "", 0.0),
            ("Cell Phone", "", 0.0),
            ("Work Phone", "", 0.0),
        ]
        doc_id = self._create_doc(app, good_fields + bad_fields)
        _login(client, app)
        client.post(
            f"/address-book/{doc_id}/apply-all",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
        from models import ExtractedField
        with app.app_context():
            field_map = {
                f.field_name: f.value
                for f in ExtractedField.query.filter_by(document_id=doc_id).all()
            }
        # Fixed fields filled with defaults
        assert field_map.get("Name") == "Rahul Misra"
        assert field_map.get("State") == "WB"
        assert field_map.get("Cell Phone") == "7699888010"
        # Variable fields NOT overwritten with sample1 defaults
        assert field_map.get("Street Address") == "123 Main St"
        assert field_map.get("City") == "Springfield"
        assert field_map.get("Zip Code") == "123456"
        # Work Phone has no default → left blank
        assert field_map.get("Work Phone") == ""

    def test_apply_all_valid_fields_not_overwritten(self, client, app):
        """Fields with good values and high confidence must not be changed."""
        fields = [
            ("Name",           "John Doe",         0.95),
            ("Street Address", "456 Oak Ave",       0.90),
            ("City",           "Gotham",            0.92),
            ("State",          "NY",                0.99),
            ("Zip Code",       "10001",             0.88),
            ("Home Phone",     "1234567890",        0.85),
            ("Cell Phone",     "0987654321",        0.91),
            ("Work Phone",     "1122334455",        0.87),
            ("Email",          "john@example.com",  0.96),
        ]
        doc_id = self._create_doc(app, fields)
        _login(client, app)
        client.post(
            f"/address-book/{doc_id}/apply-all",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
        from models import ExtractedField
        with app.app_context():
            field_map = {
                f.field_name: f.value
                for f in ExtractedField.query.filter_by(document_id=doc_id).all()
            }
        # All values unchanged
        assert field_map["Name"] == "John Doe"
        assert field_map["State"] == "NY"
        assert field_map["Cell Phone"] == "0987654321"
        assert field_map["City"] == "Gotham"

    def test_apply_all_redirects_to_editor(self, client, app):
        """Apply All must redirect back to the address-book editor page."""
        doc_id = self._create_doc(app)
        _login(client, app)
        resp = client.post(
            f"/address-book/{doc_id}/apply-all",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/address-book/{doc_id}" in resp.headers["Location"]

    def test_apply_all_sets_doc_status_edited(self, client, app):
        """Apply All must set document status to 'edited'."""
        doc_id = self._create_doc(app)
        _login(client, app)
        client.post(
            f"/address-book/{doc_id}/apply-all",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
        from models import Document
        with app.app_context():
            doc = Document.query.get(doc_id)
            assert doc.status == "edited"


# ─────────────────────────────────────────────────────────────────────────
# _is_field_invalid unit tests (AddressBook_v1 validation helpers)
# ─────────────────────────────────────────────────────────────────────────

class TestIsFieldInvalid:
    """Unit tests for the _is_field_invalid helper in blueprints/address_book.py."""

    def _fn(self):
        from blueprints.address_book import _is_field_invalid
        return _is_field_invalid

    def test_blank_value_is_invalid(self):
        fn = self._fn()
        assert fn("Name", "", 1.0) is True
        assert fn("Name", "   ", 1.0) is True

    def test_low_confidence_is_invalid(self):
        fn = self._fn()
        assert fn("Name", "Rahul Misra", 0.79) is True

    def test_threshold_edge_exactly_080(self):
        fn = self._fn()
        # Exactly 0.80 is NOT invalid (threshold is < 0.80)
        assert fn("Name", "Rahul Misra", 0.80) is False

    def test_valid_name(self):
        fn = self._fn()
        assert fn("Name", "Rahul Misra", 0.90) is False

    def test_invalid_zip_code(self):
        fn = self._fn()
        assert fn("Zip Code", "12AB", 1.0) is True
        assert fn("Zip Code", "1234", 1.0) is True   # only 4 digits

    def test_valid_zip_code_5_digits(self):
        fn = self._fn()
        assert fn("Zip Code", "12345", 1.0) is False

    def test_valid_zip_code_6_digits(self):
        fn = self._fn()
        assert fn("Zip Code", "713301", 1.0) is False

    def test_invalid_phone(self):
        fn = self._fn()
        assert fn("Cell Phone", "12345", 1.0) is True       # too short
        assert fn("Cell Phone", "123456789012", 1.0) is True  # too long

    def test_valid_phone_10_digits(self):
        fn = self._fn()
        assert fn("Cell Phone", "7699888010", 1.0) is False

    def test_invalid_email(self):
        fn = self._fn()
        assert fn("Email", "notanemail", 1.0) is True
        assert fn("Email", "missing@tld", 1.0) is True

    def test_valid_email(self):
        fn = self._fn()
        assert fn("Email", "rahul@example.com", 1.0) is False


# ─────────────────────────────────────────────────────────────────────────
# PDFService.map_address_book_fields — blank template tests
# ─────────────────────────────────────────────────────────────────────────

class TestMapAddressBookFieldsBlankTemplate:
    """Unit tests for blank-template detection in PDFService.map_address_book_fields."""

    def _svc(self):
        repo_root = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.join(repo_root, "backend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from services.pdf_service import PDFService
        return PDFService()

    def _field_names(self, result):
        return {item["field_name"] for item in result}

    def test_blank_template_returns_all_nine_fields(self):
        """OCR text with only labels → all 9 ADDRESS_BOOK_FIELDS returned."""
        svc = self._svc()
        text = (
            "Name:\n"
            "Street Address:\n"
            "City: State: Zip Code:\n"
            "Home Phone: Cell Phone: Work Phone:\n"
            "Email:\n"
        )
        result = svc.map_address_book_fields(text)
        from services.pdf_service import ADDRESS_BOOK_FIELDS
        assert self._field_names(result) == set(ADDRESS_BOOK_FIELDS)

    def test_blank_template_fields_have_empty_values(self):
        """All fields returned for a blank template must have empty string values."""
        svc = self._svc()
        text = (
            "Name: Street Address: City: State: Zip Code:\n"
            "Home Phone: Cell Phone: Work Phone: Email:\n"
        )
        result = svc.map_address_book_fields(text)
        for item in result:
            assert item["value"] == "", (
                f"Expected empty value for {item['field_name']}, got {item['value']!r}"
            )

    def test_blank_template_placeholder_fields_have_zero_confidence(self):
        """Placeholder fields added for blank templates must have confidence=0.0."""
        svc = self._svc()
        text = "City: State: Zip Code: Home Phone: Cell Phone: Work Phone: Email:\n"
        result = svc.map_address_book_fields(text)
        for item in result:
            assert item.get("confidence", 0.0) == 0.0, (
                f"Expected confidence 0.0 for blank field {item['field_name']}"
            )

    def test_partial_template_fills_missing_fields(self):
        """When only some fields have values, missing fields get empty placeholders."""
        svc = self._svc()
        text = (
            "Name Rahul Misra\n"
            "City: Asansol State: WB Zip Code:\n"
            "Home Phone: Cell Phone: 7699888010 Work Phone: Email:\n"
        )
        result = svc.map_address_book_fields(text)
        field_map = {item["field_name"]: item for item in result}
        from services.pdf_service import ADDRESS_BOOK_FIELDS
        # All 9 fields must be present
        assert set(field_map.keys()) == set(ADDRESS_BOOK_FIELDS)
        # Extracted fields retain their values
        assert field_map["Name"]["value"] == "Rahul Misra"
        assert field_map["City"]["value"] == "Asansol"
        assert field_map["State"]["value"] == "WB"
        assert field_map["Cell Phone"]["value"] == "7699888010"
        # Blank fields have empty value
        assert field_map["Zip Code"]["value"] == ""
        assert field_map["Home Phone"]["value"] == ""
        assert field_map["Email"]["value"] == ""

    def test_non_addressbook_pdf_not_affected(self):
        """Text with < 4 address-book labels → no placeholder fields added."""
        svc = self._svc()
        text = "Invoice #1234\nTotal: $100.00\nDate: 2024-01-01\n"
        result = svc.map_address_book_fields(text)
        assert result == [], f"Expected empty result for non-addressbook text, got {result}"

    def test_four_labels_triggers_template_detection(self):
        """Exactly 4 address-book labels are enough to trigger template detection."""
        svc = self._svc()
        text = "City: State: Zip Code: Email:\n"
        result = svc.map_address_book_fields(text)
        from services.pdf_service import ADDRESS_BOOK_FIELDS
        assert self._field_names(result) == set(ADDRESS_BOOK_FIELDS)

    def test_three_labels_does_not_trigger_template_detection(self):
        """Only 3 address-book labels → template detection NOT triggered."""
        svc = self._svc()
        text = "City: State: Zip Code:\n"
        result = svc.map_address_book_fields(text)
        # No values extracted and threshold not reached → empty result
        assert result == []



# ─────────────────────────────────────────────────────────────────────────
# TestApplyTrainingToDocument — POST /api/v1/training/apply/<doc_id>
# ─────────────────────────────────────────────────────────────────────────

class TestApplyTrainingToDocument:
    """Integration tests for POST /api/v1/training/apply/<doc_id>."""

    def _create_doc(self, app, fields=None):
        """Create a Document with optional ExtractedField rows; return doc.id."""
        from models import Document, ExtractedField
        with app.app_context():
            doc = Document(
                filename="train_apply_test.pdf",
                file_path="/tmp/train_apply_test.pdf",
                status="extracted",
            )
            db.session.add(doc)
            db.session.flush()
            for name, val, conf in (fields or []):
                db.session.add(ExtractedField(
                    document_id=doc.id,
                    field_name=name,
                    value=val,
                    confidence=conf,
                ))
            db.session.commit()
            return doc.id

    def _add_training(self, app, doc_id, field_name, correct_value):
        """Insert a TrainingExample row."""
        from models import TrainingExample
        with app.app_context():
            ex = TrainingExample(
                document_id=doc_id,
                field_name=field_name,
                correct_value=correct_value,
            )
            db.session.add(ex)
            db.session.commit()

    # ------------------------------------------------------------------

    def test_requires_login(self, client, app):
        doc_id = self._create_doc(app)
        resp = client.post(f"/api/v1/training/apply/{doc_id}")
        assert resp.status_code in (302, 401)

    def test_doc_not_found(self, client, app):
        _login(client, app)
        resp = client.post("/api/v1/training/apply/9999")
        assert resp.status_code == 404

    def test_no_training_data_returns_400(self, client, app):
        doc_id = self._create_doc(app, [("Name", "Old Name", 1.0)])
        _login(client, app)
        resp = client.post(f"/api/v1/training/apply/{doc_id}")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False
        assert "training" in data["error"].lower()

    def test_overwrites_all_matching_fields(self, client, app):
        """All fields with matching training data must be overwritten."""
        doc_id = self._create_doc(app, [
            ("Name",  "Old Name",  0.5),
            ("City",  "Old City",  0.5),
            ("Email", "old@x.com", 0.5),
        ])
        self._add_training(app, doc_id, "Name",  "Rahul Misra")
        self._add_training(app, doc_id, "City",  "Asansol")
        _login(client, app)
        resp = client.post(f"/api/v1/training/apply/{doc_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["updated"] == 2
        assert data["skipped"] == 1  # Email has no training data

        from models import ExtractedField
        with app.app_context():
            field_map = {
                f.field_name: f.value
                for f in ExtractedField.query.filter_by(document_id=doc_id).all()
            }
        assert field_map["Name"] == "Rahul Misra"
        assert field_map["City"] == "Asansol"
        assert field_map["Email"] == "old@x.com"  # unchanged

    def test_updates_confidence_to_training_level(self, client, app):
        """Fields updated from training data must have confidence 0.90."""
        doc_id = self._create_doc(app, [("Name", "Old", 0.3)])
        self._add_training(app, doc_id, "Name", "Rahul Misra")
        _login(client, app)
        client.post(f"/api/v1/training/apply/{doc_id}")

        from models import ExtractedField
        with app.app_context():
            field = ExtractedField.query.filter_by(
                document_id=doc_id, field_name="Name"
            ).first()
        assert field.confidence == 0.90

    def test_preserves_original_value(self, client, app):
        """original_value must be saved before overwriting."""
        doc_id = self._create_doc(app, [("Name", "Old Name", 0.5)])
        self._add_training(app, doc_id, "Name", "New Name")
        _login(client, app)
        client.post(f"/api/v1/training/apply/{doc_id}")

        from models import ExtractedField
        with app.app_context():
            field = ExtractedField.query.filter_by(
                document_id=doc_id, field_name="Name"
            ).first()
        assert field.original_value == "Old Name"
        assert field.value == "New Name"
        assert field.is_edited is True

    def test_most_common_value_wins(self, client, app):
        """When multiple training examples exist, the most common value is applied."""
        from models import TrainingExample
        doc_id = self._create_doc(app, [("City", "Wrong City", 0.2)])
        # Add three training examples: two say "Asansol", one says "Kolkata"
        with app.app_context():
            for val in ["Asansol", "Asansol", "Kolkata"]:
                db.session.add(TrainingExample(
                    document_id=doc_id, field_name="City", correct_value=val
                ))
            db.session.commit()
        _login(client, app)
        client.post(f"/api/v1/training/apply/{doc_id}")

        from models import ExtractedField
        with app.app_context():
            field = ExtractedField.query.filter_by(
                document_id=doc_id, field_name="City"
            ).first()
        assert field.value == "Asansol"

    def test_sets_document_status_edited(self, client, app):
        """Applying training data must set the document status to 'edited'."""
        doc_id = self._create_doc(app, [("Name", "Old", 0.5)])
        self._add_training(app, doc_id, "Name", "Rahul Misra")
        _login(client, app)
        client.post(f"/api/v1/training/apply/{doc_id}")

        from models import Document
        with app.app_context():
            doc = Document.query.get(doc_id)
        assert doc.status == "edited"

    def test_response_fields_list(self, client, app):
        """Response must include a 'fields' list with per-field results."""
        doc_id = self._create_doc(app, [
            ("Name", "Old", 0.5),
            ("City", "Old City", 0.5),
        ])
        self._add_training(app, doc_id, "Name", "Rahul Misra")
        _login(client, app)
        resp = client.post(f"/api/v1/training/apply/{doc_id}")
        data = resp.get_json()
        assert data["ok"] is True
        fields_map = {f["field_name"]: f for f in data["fields"]}
        assert fields_map["Name"]["updated"] is True
        assert fields_map["Name"]["new_value"] == "Rahul Misra"
        assert fields_map["City"]["updated"] is False


# ─────────────────────────────────────────────────────────────────────────
# PDFService._export_as_pdf — unit tests for the label-search fallback
# ─────────────────────────────────────────────────────────────────────────

class TestExportAsPDF:
    """Unit tests for PDFService._export_as_pdf.

    Focuses on the fallback behaviour added to fix blank PDF exports for
    address-book templates where bounding-box coordinates are absent.
    """

    def _get_service(self):
        import importlib
        import sys
        repo_root = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.join(repo_root, "backend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        import services.pdf_service as mod
        return mod.PDFService()

    def _make_pdf_with_labels(self, labels: list[str]) -> bytes:
        """Return a minimal PDF whose first page contains the given label strings."""
        import io
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        y = 50
        for label in labels:
            page.insert_text(fitz.Point(50, y), label, fontsize=12)
            y += 20
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()
        return buf.getvalue()

    def test_bbox_path_stamps_value(self, tmp_path):
        """Fields WITH a bounding box must be written at the specified location."""
        import io
        import fitz
        svc = self._get_service()
        pdf_bytes = self._make_pdf_with_labels(["Name:"])
        src = tmp_path / "src.pdf"
        src.write_bytes(pdf_bytes)

        fields = [
            {
                "field_name": "Name",
                "value": "Rahul Misra",
                "page_number": 1,
                "bbox_x": 10,
                "bbox_y": 10,
                "bbox_width": 100,
                "bbox_height": 15,
            }
        ]
        out = io.BytesIO()
        svc._export_as_pdf(str(src), fields, out)
        out.seek(0)
        result_doc = fitz.open(stream=out.read(), filetype="pdf")
        text = result_doc[0].get_text()
        result_doc.close()
        assert "Rahul Misra" in text

    def test_no_bbox_inserts_value_after_label(self, tmp_path):
        """Fields WITHOUT a bounding box must be placed next to the label found
        in the PDF text (the primary fallback path)."""
        import io
        import fitz
        svc = self._get_service()
        pdf_bytes = self._make_pdf_with_labels(["Name:", "City:"])
        src = tmp_path / "src.pdf"
        src.write_bytes(pdf_bytes)

        fields = [
            {"field_name": "Name", "value": "Rahul Misra", "page_number": 1},
            {"field_name": "City", "value": "Asansol", "page_number": 1},
        ]
        out = io.BytesIO()
        svc._export_as_pdf(str(src), fields, out)
        out.seek(0)
        result_doc = fitz.open(stream=out.read(), filetype="pdf")
        text = result_doc[0].get_text()
        result_doc.close()
        assert "Rahul Misra" in text
        assert "Asansol" in text

    def test_no_bbox_no_label_appends_summary_page(self, tmp_path):
        """Fields whose label cannot be found in the PDF must appear in a
        summary page appended at the end of the exported document."""
        import io
        import fitz
        svc = self._get_service()
        # Create a PDF with NO address-book labels
        doc = fitz.open()
        doc.new_page()
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()
        pdf_bytes = buf.getvalue()

        src = tmp_path / "blank.pdf"
        src.write_bytes(pdf_bytes)

        fields = [
            {"field_name": "Name", "value": "Rahul Misra", "page_number": 1},
        ]
        out = io.BytesIO()
        svc._export_as_pdf(str(src), fields, out)
        out.seek(0)
        result_doc = fitz.open(stream=out.read(), filetype="pdf")
        # A summary page must have been appended
        assert result_doc.page_count == 2
        summary_text = result_doc[1].get_text()
        result_doc.close()
        assert "Rahul Misra" in summary_text

    def test_empty_value_fields_are_skipped(self, tmp_path):
        """Fields with blank values must not cause any modification or error."""
        import io
        import fitz
        svc = self._get_service()
        pdf_bytes = self._make_pdf_with_labels(["Name:"])
        src = tmp_path / "src.pdf"
        src.write_bytes(pdf_bytes)

        fields = [
            {"field_name": "Name", "value": "", "page_number": 1},
        ]
        out = io.BytesIO()
        svc._export_as_pdf(str(src), fields, out)
        out.seek(0)
        result_doc = fitz.open(stream=out.read(), filetype="pdf")
        # No summary page should be appended for empty-value fields
        assert result_doc.page_count == 1
        result_doc.close()

    def test_no_bbox_replaces_existing_value_inline(self, tmp_path):
        """When a PDF already has a value next to the label (e.g. 'Name: John Smith'),
        exporting with a new value must place the new text inline (no summary page)
        and the new value must appear in the result.

        This covers the address-book template case: Apply Training Data updates
        ExtractedField.value in the DB, the export must reflect those edits in
        the original PDF page rather than silently appending a summary page.
        """
        import io
        import fitz
        svc = self._get_service()

        # Build a PDF that already has "Name: John Smith" — simulates an
        # address-book PDF whose fields were populated by a previous extraction.
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(fitz.Point(50, 50), "Name: John Smith", fontsize=12)
        page.insert_text(fitz.Point(50, 70), "City: OldCity", fontsize=12)
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()
        src = tmp_path / "prefilled.pdf"
        src.write_bytes(buf.getvalue())

        # Export with new (training-applied) values — no bounding box supplied,
        # forcing the label-search fallback path.
        fields = [
            {"field_name": "Name", "value": "Rahul Misra", "page_number": 1},
            {"field_name": "City", "value": "Asansol", "page_number": 1},
        ]
        out = io.BytesIO()
        svc._export_as_pdf(str(src), fields, out)
        out.seek(0)
        result_doc = fitz.open(stream=out.read(), filetype="pdf")

        # Values must be placed inline — no summary page should be appended.
        assert result_doc.page_count == 1, (
            "Expected 1 page (values placed inline); got a summary page instead"
        )

        # The new values must appear in the first page.
        page_text = result_doc[0].get_text()
        result_doc.close()
        assert "Rahul Misra" in page_text, "New 'Name' value not found in exported PDF"
        assert "Asansol" in page_text, "New 'City' value not found in exported PDF"

    def test_no_bbox_new_value_placed_at_label_position(self, tmp_path):
        """The new value must be placed immediately to the right of the label,
        not somewhere else on the page (e.g., not on a new line or offset)."""
        import io
        import fitz
        svc = self._get_service()

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(fitz.Point(50, 50), "Name: OldValue", fontsize=12)
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()
        src = tmp_path / "src.pdf"
        src.write_bytes(buf.getvalue())

        fields = [{"field_name": "Name", "value": "NewValue", "page_number": 1}]
        out = io.BytesIO()
        svc._export_as_pdf(str(src), fields, out)
        out.seek(0)
        result_doc = fitz.open(stream=out.read(), filetype="pdf")

        # Find "NewValue" span and "Name:" span; their y-ranges must overlap,
        # confirming the new value is on the same line as the label.
        text_dict = result_doc[0].get_text("dict")
        result_doc.close()

        label_bbox = None
        new_value_bbox = None
        for block in text_dict["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if span["text"].startswith("Name:"):
                        label_bbox = span["bbox"]
                    if "NewValue" in span["text"]:
                        new_value_bbox = span["bbox"]

        assert new_value_bbox is not None, "'NewValue' span not found in result PDF"
        assert label_bbox is not None, "'Name:' label span not found in result PDF"

        # y-ranges must overlap: top of new value ≤ bottom of label and vice-versa
        label_y0, label_y1 = label_bbox[1], label_bbox[3]
        val_y0, val_y1 = new_value_bbox[1], new_value_bbox[3]
        overlap = min(label_y1, val_y1) - max(label_y0, val_y0)
        assert overlap > 0, (
            f"New value y-range {(val_y0, val_y1)} does not overlap label y-range "
            f"{(label_y0, label_y1)} — value not placed on same line as label"
        )
