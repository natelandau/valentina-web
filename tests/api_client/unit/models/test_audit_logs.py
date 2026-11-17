"""Tests for vweb.api_client.models.audit_logs."""

from vweb.api_client.models.audit_logs import AuditLog, AuditLogDetail


class TestAuditLog:
    """Tests for AuditLog model."""

    def test_valid_audit_log(self):
        """Verify valid audit log creation with all required fields."""
        log = AuditLog(
            id="log123",
            date_created="2024-01-15T10:30:00Z",
            entity_type="CAMPAIGN",
            operation="CREATE",
            target_entity_id="campaign456",
            description="Created campaign 'Test Campaign'",
            changes=None,
            company_id="company789",
        )
        assert log.id == "log123"
        assert log.entity_type == "CAMPAIGN"
        assert log.operation == "CREATE"
        assert log.target_entity_id == "campaign456"
        assert log.company_id == "company789"

    def test_optional_fields_default_to_none(self):
        """Verify optional fields default to None."""
        log = AuditLog(
            id="log123",
            date_created="2024-01-15T10:30:00Z",
            entity_type="USER",
            operation="UPDATE",
            target_entity_id="user456",
            description="Updated user",
            changes={"name": {"old": "Alice", "new": "Bob"}},
            company_id="company789",
        )
        assert log.acting_user_id is None
        assert log.user_id is None
        assert log.campaign_id is None
        assert log.book_id is None
        assert log.chapter_id is None
        assert log.character_id is None
        assert log.request_id is None

    def test_changes_dict(self):
        """Verify changes field accepts dict with old/new structure."""
        changes = {
            "name": {"old": "Old Name", "new": "New Name"},
            "description": {"old": None, "new": "A description"},
        }
        log = AuditLog(
            id="log123",
            date_created="2024-01-15T10:30:00Z",
            entity_type="COMPANY",
            operation="UPDATE",
            target_entity_id="company456",
            description="Updated company",
            changes=changes,
            company_id="company789",
        )
        assert log.changes == changes
        assert log.changes["name"]["old"] == "Old Name"

    def test_all_optional_fields_populated(self):
        """Verify all optional fields can be set."""
        log = AuditLog(
            id="log123",
            date_created="2024-01-15T10:30:00Z",
            entity_type="CHARACTER",
            operation="DELETE",
            target_entity_id="char456",
            description="Deleted character",
            changes=None,
            company_id="company789",
            acting_user_id="user111",
            user_id="user222",
            campaign_id="camp333",
            book_id="book444",
            chapter_id="chap555",
            character_id="char666",
            request_id="req777",
        )
        assert log.acting_user_id == "user111"
        assert log.user_id == "user222"
        assert log.campaign_id == "camp333"
        assert log.book_id == "book444"
        assert log.chapter_id == "chap555"
        assert log.character_id == "char666"
        assert log.request_id == "req777"


class TestAuditLogDetail:
    """Tests for AuditLogDetail model."""

    def test_inherits_audit_log_fields(self):
        """Verify AuditLogDetail includes all AuditLog fields."""
        detail = AuditLogDetail(
            id="log123",
            date_created="2024-01-15T10:30:00Z",
            entity_type="CAMPAIGN",
            operation="CREATE",
            target_entity_id="campaign456",
            description="Created campaign",
            changes=None,
            company_id="company789",
        )
        assert detail.id == "log123"
        assert detail.entity_type == "CAMPAIGN"
        assert detail.operation == "CREATE"

    def test_detail_fields_default_to_none(self):
        """Verify request detail fields default to None."""
        detail = AuditLogDetail(
            id="log123",
            date_created="2024-01-15T10:30:00Z",
            entity_type="USER",
            operation="UPDATE",
            target_entity_id="user456",
            description="Updated user",
            changes=None,
            company_id="company789",
        )
        assert detail.method is None
        assert detail.url is None
        assert detail.request_json is None
        assert detail.request_body is None
        assert detail.path_params is None
        assert detail.query_params is None
        assert detail.operation_id is None
        assert detail.handler_name is None
        assert detail.summary is None

    def test_detail_fields_populated(self):
        """Verify request detail fields can be set."""
        detail = AuditLogDetail(
            id="log123",
            date_created="2024-01-15T10:30:00Z",
            entity_type="CHARACTER",
            operation="CREATE",
            target_entity_id="char456",
            description="Created character",
            changes=None,
            company_id="company789",
            method="POST",
            url="/api/v1/companies/c1/users/u1/campaigns/camp1/characters",
            request_json={"name": "Dracula", "character_class": "VAMPIRE"},
            request_body='{"name": "Dracula"}',
            path_params={"company_id": "c1", "user_id": "u1"},
            query_params={"include": "traits"},
            operation_id="create_character",
            handler_name="CharactersHandler.create",
            summary="Create a new character in a campaign",
        )
        assert detail.method == "POST"
        assert detail.request_json == {"name": "Dracula", "character_class": "VAMPIRE"}
        assert detail.request_body == '{"name": "Dracula"}'
        assert detail.path_params == {"company_id": "c1", "user_id": "u1"}
        assert detail.query_params == {"include": "traits"}
        assert detail.operation_id == "create_character"
        assert detail.handler_name == "CharactersHandler.create"
        assert detail.summary == "Create a new character in a campaign"
