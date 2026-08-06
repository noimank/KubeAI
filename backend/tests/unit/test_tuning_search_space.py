import pytest
from optuna.distributions import CategoricalDistribution, FloatDistribution, IntDistribution

from app.core.optuna import json_search_space_to_distributions


class TestJsonSearchSpaceToDistributions:
    def test_float_maps_to_float_distribution(self):
        dists, fixed = json_search_space_to_distributions(
            {"lr": {"type": "float", "low": 0.0001, "high": 0.1, "log": True}}
        )
        d = dists["lr"]
        assert isinstance(d, FloatDistribution)
        assert d.low == 0.0001
        assert d.high == 0.1
        assert d.log is True
        assert fixed == {}

    def test_int_maps_to_int_distribution_with_step(self):
        dists, _ = json_search_space_to_distributions({"bs": {"type": "int", "low": 16, "high": 128, "step": 8}})
        d = dists["bs"]
        assert isinstance(d, IntDistribution)
        assert d.low == 16
        assert d.high == 128
        assert d.step == 8

    def test_int_without_step_defaults_to_1(self):
        dists, _ = json_search_space_to_distributions({"bs": {"type": "int", "low": 16, "high": 128}})
        assert dists["bs"].step == 1

    def test_categorical_maps_to_categorical_distribution(self):
        dists, _ = json_search_space_to_distributions({"opt": {"type": "categorical", "choices": ["adam", "sgd"]}})
        d = dists["opt"]
        assert isinstance(d, CategoricalDistribution)
        assert list(d.choices) == ["adam", "sgd"]

    def test_fixed_goes_to_fixed_params_not_distributions(self):
        dists, fixed = json_search_space_to_distributions({"dropout": {"type": "fixed", "value": 0.5}})
        assert dists == {}
        assert fixed == {"dropout": 0.5}

    def test_invalid_type_raises_value_error(self):
        with pytest.raises(ValueError, match="不支持的搜索空间类型"):
            json_search_space_to_distributions({"x": {"type": "unknown"}})

    def test_mixed_search_space(self):
        ss = {
            "lr": {"type": "float", "low": 1e-4, "high": 0.1},
            "opt": {"type": "categorical", "choices": ["a", "b"]},
            "seed": {"type": "fixed", "value": 42},
        }
        dists, fixed = json_search_space_to_distributions(ss)
        assert set(dists.keys()) == {"lr", "opt"}
        assert fixed == {"seed": 42}
