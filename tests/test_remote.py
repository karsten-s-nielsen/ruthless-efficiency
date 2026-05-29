from ruthless.remote import RemoteObjective, RemoteRef
from ruthless.result import Candidate


class _Remote:  # structural — does NOT inherit the Protocol
    def evaluate(self, candidate: Candidate):
        return {"loss": 0.0}

    @property
    def remote_ref(self) -> RemoteRef:
        return RemoteRef(entrypoint="my_pkg.objectives:train_and_evaluate", package="my-pkg @ https://h/x.whl")

    epochs = 5
    seed = 42


class _Plain:
    def evaluate(self, candidate: Candidate):
        return {"loss": 0.0}


def test_remote_ref_fields():
    r = RemoteRef(entrypoint="m:f")
    assert r.entrypoint == "m:f" and r.package is None  # ssh case: no install spec


def test_remote_objective_structural_conformance():
    obj: RemoteObjective = _Remote()
    assert isinstance(obj, RemoteObjective)
    assert obj.remote_ref.entrypoint.endswith(":train_and_evaluate")
    assert obj.epochs == 5 and obj.seed == 42


def test_plain_objective_is_not_remote():
    assert not isinstance(_Plain(), RemoteObjective)  # name-only check still distinguishes remote_ref/epochs/seed
