import textwrap

from ruthless.config import FitnessConfig
from ruthless.errors import FatalEvaluationError, TransientEvaluationError
from ruthless.remote import RemoteRef
from ruthless.strategies.evolve_.evaluator import EvolveEvaluator
from ruthless.strategies.evolve_.sandbox import ValidationProfile

_PROFILE = ValidationProfile(
    patch_method="_embed",
    patch_signature=["self", "x", "y"],
    return_shape="(batch, hidden_dim)",
    known_model_attrs=frozenset({"linear"}),
    allowed_namespaces=frozenset({"torch", "math"}),
    layers_args=["hidden_dim"],
    rejected_builtins=frozenset({"eval", "exec", "open", "__import__"}),
)


class _FakeObjective:
    def evaluate(self, candidate):
        return {}

    @property
    def remote_ref(self):
        return RemoteRef(entrypoint="m:f")

    epochs = 5
    seed = 42


class _FakeBackend:
    def __init__(self, *, metrics=None, raises=None):
        self.metrics = metrics or {"primary": 0.8, "aux": 0.4}
        self.raises = raises
        self.candidate = None

    def evaluate(self, candidate, objective, *, timeout=None):
        self.candidate = candidate
        if self.raises is not None:
            raise self.raises
        return dict(self.metrics)

    def available(self):
        return True


def _write(tmp_path, src):
    p = tmp_path / "candidate.py"
    p.write_text(textwrap.dedent(src), encoding="utf-8")
    return str(p)


def _evaluator(backend, **kw):
    return EvolveEvaluator(
        backend=backend,
        objective=_FakeObjective(),
        fitness_config=FitnessConfig(primary="primary", combined_weights={"primary": 0.75, "aux": 0.25}),
        validation_profile=_PROFILE,
        code_evolution=True,
        **kw,
    )


def test_evaluate_dispatches_and_computes_combined_score(tmp_path):
    backend = _FakeBackend(metrics={"primary": 1.0, "aux": 0.0})
    path = _write(tmp_path, 'config = {"hidden_dim": 256}\n')
    result = _evaluator(backend).evaluate(path)
    assert result.metrics["combined_score"] == 0.75  # 0.75*1.0 + 0.25*0.0
    assert backend.candidate is not None
    assert backend.candidate.params == {"hidden_dim": 256}
    assert backend.candidate.program is None  # config-only -> no program


def test_level2_passes_source_as_candidate_program(tmp_path):
    backend = _FakeBackend()
    src = """\
        config = {"hidden_dim": 256}

        def custom_embed(self, x, y):
            return self.linear(x) + y
    """
    path = _write(tmp_path, src)
    _evaluator(backend).evaluate(path)
    assert backend.candidate is not None and backend.candidate.program is not None
    assert "custom_embed" in backend.candidate.program


def test_sandbox_rejects_before_dispatch(tmp_path):
    backend = _FakeBackend()
    src = """\
        config = {"hidden_dim": 256}

        def custom_embed(self, x, y):
            import os
            return x
    """
    result = _evaluator(backend).evaluate(_write(tmp_path, src))
    assert result.metrics["combined_score"] == 0.0 and result.metrics["error"] == 1.0
    assert result.artifacts["failure_kind"] == "objective"
    assert backend.candidate is None  # never dispatched


def test_backend_fatal_maps_to_objective_sentinel(tmp_path):
    backend = _FakeBackend(raises=FatalEvaluationError("crash"))
    result = _evaluator(backend).evaluate(_write(tmp_path, 'config = {"hidden_dim": 256}\n'))
    assert result.metrics["combined_score"] == 0.0
    assert result.artifacts["failure_kind"] == "objective"


def test_backend_transient_maps_to_infra_sentinel(tmp_path):
    backend = _FakeBackend(raises=TransientEvaluationError("ssh down"))
    result = _evaluator(backend).evaluate(_write(tmp_path, 'config = {"hidden_dim": 256}\n'))
    assert result.metrics["combined_score"] == 0.0
    assert result.artifacts["failure_kind"] == "infra"


def test_injected_search_space_validator_blocks(tmp_path):
    backend = _FakeBackend()
    ev = _evaluator(backend, search_space_validator=lambda cfg: (False, "hidden_dim too large"))
    result = ev.evaluate(_write(tmp_path, 'config = {"hidden_dim": 99999}\n'))
    assert result.metrics["combined_score"] == 0.0
    assert "hidden_dim too large" in str(result.artifacts["error"])
    assert backend.candidate is None
