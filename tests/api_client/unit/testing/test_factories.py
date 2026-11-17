"""Tests for polyfactory model factories."""

import pytest

import vweb.api_client.testing
from vweb.api_client.models import CounterTracker, Health, StainsTracker
from vweb.api_client.testing._factories import (
    AssetFactory,
    CampaignBookFactory,
    CampaignChapterFactory,
    CampaignExperienceFactory,
    CampaignFactory,
    CharacterConceptFactory,
    CharacterDetailFactory,
    CharacterFactory,
    CharacterTraitFactory,
    CharacterTraitValueOptionsResponseFactory,
    ChargenSessionResponseFactory,
    CompanyFactory,
    CompanyPermissionsFactory,
    CounterTrackerFactory,
    DicerollFactory,
    DictionaryTermFactory,
    HealthFactory,
    HealthLevelFactory,
    IdentityResolutionFactory,
    InventoryItemFactory,
    NewCompanyResponseFactory,
    NoteFactory,
    QuickrollFactory,
    RollStatisticsFactory,
    SheetSectionFactory,
    StainsTrackerFactory,
    SystemHealthFactory,
    TraitCategoryFactory,
    TraitFactory,
    UserFactory,
    VampireClanFactory,
    WerewolfAuspiceFactory,
    WerewolfTribeFactory,
)


class TestFactoriesBuildValidModels:
    """Each factory should produce a valid model instance."""

    @pytest.mark.parametrize(
        "factory_cls",
        [
            AssetFactory,
            CampaignBookFactory,
            CampaignChapterFactory,
            CampaignExperienceFactory,
            CampaignFactory,
            CharacterConceptFactory,
            CharacterFactory,
            CharacterTraitFactory,
            CharacterTraitValueOptionsResponseFactory,
            ChargenSessionResponseFactory,
            CompanyFactory,
            CompanyPermissionsFactory,
            DicerollFactory,
            DictionaryTermFactory,
            IdentityResolutionFactory,
            InventoryItemFactory,
            NewCompanyResponseFactory,
            NoteFactory,
            QuickrollFactory,
            RollStatisticsFactory,
            SheetSectionFactory,
            SystemHealthFactory,
            TraitCategoryFactory,
            TraitFactory,
            UserFactory,
            VampireClanFactory,
            WerewolfAuspiceFactory,
            WerewolfTribeFactory,
        ],
    )
    def test_factory_builds_valid_instance(self, factory_cls):
        """Each factory should produce a valid instance of its model."""
        instance = factory_cls.build()
        assert instance is not None
        assert isinstance(instance, factory_cls.__model__)

    def test_diceroll_factory_dice_modifier_defaults_to_zero(self):
        """Verify DicerollFactory builds with a zero dice_modifier."""
        assert DicerollFactory.build().dice_modifier == 0

    def test_factory_accepts_overrides(self):
        """Factories should accept field overrides."""
        campaign = CampaignFactory.build(name="Custom Name")
        assert campaign.name == "Custom Name"

    def test_factory_batch(self):
        """Factories should support batch creation."""
        campaigns = CampaignFactory.batch(3)
        assert len(campaigns) == 3
        assert all(isinstance(c, CampaignFactory.__model__) for c in campaigns)


class TestTrackerFactories:
    """Tracker and health factories should round-trip through their models."""

    @pytest.mark.parametrize(
        "factory_cls",
        [CounterTrackerFactory, StainsTrackerFactory, HealthLevelFactory, HealthFactory],
    )
    def test_tracker_factory_round_trips(self, factory_cls):
        """Verify built instances survive JSON serialization and validation."""
        instance = factory_cls.build()
        model = factory_cls.__model__
        assert model.model_validate(instance.model_dump(mode="json")) == instance

    @pytest.mark.parametrize("factory_cls", [CharacterTraitFactory, CharacterFactory])
    def test_models_with_tracker_fields_round_trip(self, factory_cls):
        """Verify built characters and traits survive JSON serialization and validation."""
        for _ in range(20):
            instance = factory_cls.build()
            model = factory_cls.__model__
            assert model.model_validate(instance.model_dump(mode="json")) == instance

    @pytest.mark.parametrize("factory_cls", [CharacterFactory, CharacterDetailFactory])
    def test_character_factory_always_has_health(self, factory_cls):
        """Verify fake characters carry health, as the API always sends it."""
        for _ in range(20):
            assert isinstance(factory_cls.build().health, Health)

    def test_character_trait_factory_varies_tracker(self):
        """Verify fake traits produce every tracker variant and no other."""
        kinds = {type(CharacterTraitFactory.build().tracker) for _ in range(200)}
        assert kinds == {CounterTracker, StainsTracker, type(None)}

    def test_damage_tracker_factory_removed(self):
        """Verify the testing module no longer exports a damage tracker factory."""
        assert not hasattr(vweb.api_client.testing, "DamageTrackerFactory")

    def test_health_factory_damage_fits_track(self):
        """Verify fake health always reports a damage count within its size."""
        for _ in range(50):
            health = HealthFactory.build()
            assert isinstance(health.damage, int)
            assert 0 <= health.damage <= health.size

    def test_health_factory_levels_match_damage(self):
        """Verify fake V4 levels mark the first boxes up to the damage count."""
        seen_levels = False
        for _ in range(50):
            health = HealthFactory.build()
            if health.levels is None:
                continue
            seen_levels = True
            assert len(health.levels) == health.size
            assert [level.marked for level in health.levels] == (
                [True] * health.damage + [False] * (health.size - health.damage)
            )
        assert seen_levels

    def test_health_factory_produces_v5_shape(self):
        """Verify fake health sometimes has no levels, as on V5."""
        assert any(HealthFactory.build().levels is None for _ in range(50))

    def test_health_factory_legacy_damage_none(self):
        """Verify fake health with no damage count builds levels with unknown marks."""
        for _ in range(20):
            health = HealthFactory.build(damage=None)
            assert health.damage is None
            assert health.levels is None or all(lvl.marked is None for lvl in health.levels)

    def test_health_level_factory_sets_marked(self):
        """Verify fake health levels report a marked flag, as the current API does."""
        assert all(isinstance(HealthLevelFactory.build().marked, bool) for _ in range(20))

    def test_health_factory_keeps_overrides(self):
        """Verify overridden fields are kept and levels derive from them."""
        health = HealthFactory.build(size=4, damage=1)
        assert health.size == 4
        assert health.damage == 1
        if health.levels is not None:
            assert [level.marked for level in health.levels] == [True, False, False, False]

    def test_counter_and_stains_factories_stay_in_range(self):
        """Verify fake counters and stains respect their capacity."""
        for _ in range(50):
            counter = CounterTrackerFactory.build()
            assert 0 <= counter.current <= counter.size
            stains = StainsTrackerFactory.build()
            assert stains.stain_capacity == 10 - stains.humanity
            assert 0 <= stains.stains <= stains.stain_capacity

    @pytest.mark.parametrize(
        "factory_cls", [CounterTrackerFactory, StainsTrackerFactory, HealthFactory]
    )
    def test_tracker_factories_honor_seed(self, factory_cls):
        """Verify seed_random makes tracker factories reproducible."""
        factory_cls.seed_random(42)
        first = factory_cls.build()
        factory_cls.seed_random(42)
        assert factory_cls.build() == first
