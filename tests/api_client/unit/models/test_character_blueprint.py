"""Tests for vweb.api_client.models.character_blueprint."""

from vweb.api_client.models.character_blueprint import TraitSubcategory


class TestTraitSubcategory:
    """Tests for TraitSubcategory model."""

    def test_valid_subcategory(self):
        """Verify valid subcategory creation with all fields."""
        subcategory = TraitSubcategory(
            id="subcat123",
            name="Allies",
            description="People who support the character",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            game_versions=["V5"],
            character_classes=["VAMPIRE", "WEREWOLF"],
            show_when_empty=True,
            initial_cost=1,
            upgrade_cost=2,
            requires_parent=False,
            pool=None,
            system=None,
            category_id="category123",
            category_name="Backgrounds",
            sheet_section_id="section123",
            sheet_section_name="Backgrounds",
        )

        assert subcategory.id == "subcat123"
        assert subcategory.name == "Allies"
        assert subcategory.requires_parent is False
        assert subcategory.category_id == "category123"
        assert subcategory.category_name == "Backgrounds"

    def test_optional_fields_default_to_none(self):
        """Verify optional fields default correctly."""
        subcategory = TraitSubcategory(
            id="subcat123",
            name="Allies",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            show_when_empty=True,
            initial_cost=1,
            upgrade_cost=2,
            requires_parent=False,
            category_id="category123",
            category_name="Backgrounds",
            sheet_section_id="section123",
            sheet_section_name="Backgrounds",
        )

        assert subcategory.description is None
        assert subcategory.pool is None
        assert subcategory.system is None
        assert subcategory.game_versions == []
        assert subcategory.character_classes == []

    def test_with_pool_and_system(self):
        """Verify subcategory with pool and system fields populated."""
        subcategory = TraitSubcategory(
            id="subcat123",
            name="Endowments",
            description="Hunter endowments",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            game_versions=["V5"],
            character_classes=["HUNTER"],
            show_when_empty=False,
            initial_cost=2,
            upgrade_cost=3,
            requires_parent=True,
            pool="Resolve + Composure",
            system="Requires edge activation",
            category_id="category456",
            category_name="Edges",
            sheet_section_id="section456",
            sheet_section_name="Edges",
        )

        assert subcategory.pool == "Resolve + Composure"
        assert subcategory.system == "Requires edge activation"
        assert subcategory.requires_parent is True
