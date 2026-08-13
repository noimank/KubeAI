import pytest
from optuna.distributions import CategoricalDistribution, FloatDistribution, IntDistribution
from optuna.samplers import CmaEsSampler, RandomSampler, TPESampler

from app.core.optuna import build_sampler, json_search_space_to_distributions
from app.schemas.tuning import SamplerConfig
from app.services.tuning_service import _percentile


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


class TestBuildSampler:
    def test_default_is_tpe(self):
        assert isinstance(build_sampler(None), TPESampler)

    def test_random_sampler(self):
        s = build_sampler(SamplerConfig(type="random"))
        assert isinstance(s, RandomSampler)

    def test_cmaes_sampler(self):
        s = build_sampler(SamplerConfig(type="cmaes"), distributions={"lr": FloatDistribution(1e-4, 0.1)})
        assert isinstance(s, CmaEsSampler)

    def test_tpe_forwards_multivariate_and_n_startup(self):
        s = build_sampler(SamplerConfig(type="tpe", multivariate=True, n_startup_trials=3))
        assert isinstance(s, TPESampler)
        assert s._multivariate is True
        assert s._n_startup_trials == 3

    def test_tpe_default_n_startup_trials(self):
        s = build_sampler(SamplerConfig(type="tpe"))
        assert s._n_startup_trials == 10

    def test_cmaes_rejects_categorical_space(self):
        with pytest.raises(ValueError, match="CMA-ES"):
            build_sampler(SamplerConfig(type="cmaes"), distributions={"opt": CategoricalDistribution(["a", "b"])})

    def test_cmaes_allows_float_and_int(self):
        s = build_sampler(
            SamplerConfig(type="cmaes"),
            distributions={"a": FloatDistribution(0, 1), "b": IntDistribution(1, 10)},
        )
        assert isinstance(s, CmaEsSampler)

    def test_cmaes_ignores_multivariate(self):
        # multivariate/n_startup 仅对 TPE 生效; cmaes 配置了也不报错、不生效.
        s = build_sampler(SamplerConfig(type="cmaes", multivariate=True), distributions={"a": FloatDistribution(0, 1)})
        assert isinstance(s, CmaEsSampler)

    def test_seed_forwarded_to_tpe(self):
        # 同一 seed 构造的 sampler 在 in-memory study 上采样一致 (证明 seed 生效), 异 seed 不同.
        import optuna

        d = FloatDistribution(0.0, 1.0)
        v_same_1 = optuna.create_study(sampler=build_sampler(SamplerConfig(type="tpe", seed=7))).ask({"lr": d})
        v_same_2 = optuna.create_study(sampler=build_sampler(SamplerConfig(type="tpe", seed=7))).ask({"lr": d})
        v_diff = optuna.create_study(sampler=build_sampler(SamplerConfig(type="tpe", seed=8))).ask({"lr": d})
        assert v_same_1.params["lr"] == v_same_2.params["lr"]
        assert v_same_1.params["lr"] != v_diff.params["lr"]

    def test_fixed_seed_advances_with_asked_trials(self):
        """回归: 固定 seed 重建 sampler 时按已 ask 数派生种子 (RNG 随 trial 前进).

        每次 drive tick 重建 sampler 只 ask 一次; 若不派生, 固定 seed 每次都采出 RNG 首值
        → 所有 trial 参数恒等 (用户所遇 "随机搜索每次都是同一值").
        """
        import optuna

        d = {"lr": FloatDistribution(1e-4, 0.1)}
        # asked_trials=1 → 实际种子 7+1=8, 与 RandomSampler(8) 首值一致; 与种子 7 的首值不同.
        v_advanced = (
            optuna.create_study(sampler=build_sampler(SamplerConfig(type="random", seed=7), asked_trials=1))
            .ask(d)
            .params["lr"]
        )
        v_base = optuna.create_study(sampler=RandomSampler(seed=8)).ask(d).params["lr"]
        v_no_advance = optuna.create_study(sampler=RandomSampler(seed=7)).ask(d).params["lr"]
        assert v_advanced == v_base  # 派生种子 = seed + asked_trials
        assert v_advanced != v_no_advance  # 不同 tick 不再恒等
        # 默认 asked_trials=0 → 仍用原 seed, 创建路径行为不变.
        assert (
            optuna.create_study(sampler=build_sampler(SamplerConfig(type="random", seed=7))).ask(d).params["lr"]
            == v_no_advance
        )

    def test_seed_none_ignores_asked_trials(self):
        # seed 未配置 → asked_trials 不生效, 仍构建 RandomSampler (运行时从熵采样).
        s = build_sampler(SamplerConfig(type="random", seed=None), asked_trials=5)
        assert isinstance(s, RandomSampler)


class TestPercentile:
    def test_median_is_average_for_two_points(self):
        assert _percentile([0.2, 0.3], 50.0) == 0.25

    def test_60th_percentile_two_points(self):
        assert _percentile([0.2, 0.3], 60.0) == pytest.approx(0.26)

    def test_median_odd_length(self):
        assert _percentile([0.1, 0.2, 0.3], 50.0) == 0.2

    def test_extremes(self):
        assert _percentile([0.1, 0.2, 0.3, 0.4], 0.0) == 0.1
        assert _percentile([0.1, 0.2, 0.3, 0.4], 100.0) == 0.4
