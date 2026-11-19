"""Tests for polyfactory model factories."""

import pytest

from vweb.api_client.models import CounterTracker, Health, StainsTracker
from vweb.api_client.testing._factories import (
    CharacterDetailFactory,
    CharacterFactory,
    CharacterTraitFactory,
    CounterTrackerFactory,
    HealthFactory,
    HealthLevelFactory,
    StainsTrackerFactory,
)
from vweb.api_client.testing._router import _FACTORY_MAP


@pytest.mark.parametrize(
    "factory_cls",
    sorted(_FACTORY_MAP.values(), key=lambda factory: factory.__name__),
    ids=lambda factory: factory.__name__,
)
def test_factory_output_survives_the_wire(factory_cls) -> None:
    """Verify every factory the fake serves builds models that round-trip through JSON."""
    for _ in range(5):
        instance = factory_cls.build()
        assert factory_cls.__model__.model_validate(instance.model_dump(mode="json")) == instance


class TestTrackerFactories:
    """Tracker and health factories should build data the API could send."""

    @pytest.mark.parametrize("factory_cls", [CharacterFactory, CharacterDetailFactory])
    def test_character_factory_always_has_health(self, factory_cls):
        """Verify fake characters carry health, as the API always sends it."""
        for _ in range(20):
            assert isinstance(factory_cls.build().health, Health)

    def test_character_trait_factory_varies_tracker(self):
        """Verify fake traits produce every tracker variant and no other."""
        expected = {CounterTracker, StainsTracker, type(None)}
        kinds: set[type] = set()
        for _ in range(200):
            kind = type(CharacterTraitFactory.build().tracker)
            assert kind in expected
            kinds.add(kind)
            if kinds == expected:
                break
        assert kinds == expected

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
            assert health.damage is not None
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
