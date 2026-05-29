# Structurizr DSL
workspace "ruthless-efficiency" "A general optimisation/search substrate: a pure hexagonal core + pluggable search strategies + pluggable compute backends (Phase 1A + 1B + 2 library side)." {

    model {
        user = person "Optimisation User" "A developer who writes an Objective and a search config, then runs a search programmatically or via the CLI."

        objective = softwareSystem "User Objective" "Consumer-supplied evaluation: a Candidate maps to Metrics. For remote/GPU runs, a RemoteObjective exposing a RemoteRef (install spec + train_and_evaluate entrypoint)." "External"

        configFile = softwareSystem "Config File" "A YAML file declaring the seed, strategy, and (for evolve) backend + entrypoint + hooks." "External"

        openevolve = softwareSystem "OpenEvolve" "Third-party evolutionary-search library: owns the islands/RNG/migration loop. EvolveStrategy is a thin adapter over run_evolution." "External"

        node = softwareSystem "Compute Node" "An SSH host or Hugging Face Job that installs the remote_package, imports the entrypoint, and runs train_and_evaluate." "External"

        optunalib = softwareSystem "Optuna" "Third-party hyperparameter-optimization library: owns the study/sampler/storage. OptunaStrategy wraps create_study + optimize, resuming from SQLite." "External"

        res = softwareSystem "ruthless-efficiency" "Optimisation/search substrate: pure core + RandomSearch + (1B) EvolveStrategy over OpenEvolve + a multi-backend compute pool + (2) OptunaStrategy." {

            cli = container "CLI" "Config-driven entry point: load config, resolve a trusted objective import-string, build the strategy, run it, print the report." "Python: ruthless.cli"

            config = container "Config" "Layered Pydantic config package (space/common/strategies): discriminated strategy union (random | evolve | optuna) + param-space union + BackendConfig (shell-safe SSH-field validators)." "Python: pydantic v2, pyyaml"

            random = container "RandomSearchStrategy" "Built-in zero-dependency search: seeded numpy RNG; drives the determinism gate." "Python: ruthless.strategies.random_"

            report = container "Reporting" "Renders a Result to machine JSON and a human Markdown summary." "Python: ruthless.report"

            core = container "Core & Ports" "The pure hexagon: a curated public API (ruthless.__all__) over ports, value types, error taxonomy, penalty guards, parallel map, logging, the in-process backend, remote-resolvability types, the cross-wire contract, and a shared temp-file helper." "Python: ruthless" {
                errors = component "errors" "Taxonomy: Fatal/Transient evaluation errors; classify_metric." "Python"
                result = component "result" "Candidate (hashable, read-only params, + program), Evaluation, Result, Metrics." "Python"
                wire = component "wire" "Cross-wire failure/score contract: combined_score/error/_error_text keys, worst-score sentinel, surfaced-traceback limit." "Python"
                io = component "_io" "program_to_path — uniform temp .py path-or-None for a Candidate's program (shared by backends + strategies)." "Python"
                objectivePort = component "objective (port)" "Objective Protocol + CachedObjective (invariant-prep / per-trial-patch + patch_params)." "Python Protocol"
                backendPort = component "backend (port)" "ComputeBackend Protocol (evaluate(candidate, objective, *, timeout)) + InProcessBackend." "Python"
                strategyPort = component "strategy (port)" "Direction + the SearchStrategy Protocol." "Python Protocol"
                remote = component "remote" "RemoteRef (install spec + entrypoint) + RemoteObjective Protocol — remote-execution opt-in." "Python"
                guards = component "guards" "penalty_metrics — recorded penalty scores." "Python"
                parallel = component "parallel" "map_work_units — intra-objective thread/process map." "Python"
                logging = component "logging" "get_logger — namespaced ruthless.* loggers." "Python"
                testing = component "testing" "assert_cache_equivalence — proves a CachedObjective's fast path == full recompute (consumer harness)." "Python"

                objectivePort -> result "Uses Candidate / Metrics"
                backendPort -> objectivePort "Calls evaluate (in-process)"
                backendPort -> result "Returns Metrics"
                strategyPort -> backendPort "Typed against the backend port"
                strategyPort -> result "Returns a Result"
                remote -> result "References Candidate / Metrics"
                guards -> result "Builds penalty Metrics"
                errors -> result "References the Metrics scale"
                testing -> objectivePort "Checks a CachedObjective"
                io -> result "Reads Candidate.program"
            }

            backends = container "Backends [extra]" "Inter-candidate compute dispatch on the single port. Priority-ordered pool + adapters; raise Transient/Fatal (never a sentinel)." "Python: ruthless.backends" {
                pool = component "pool" "BackendPool: priority-queue dispatch + bounded transient-retry." "Python"
                base = component "base" "parse_last_json_line, is_objective_failure, require_remote; re-exports program_to_path (from core _io) + the wire failure-marker contract." "Python"
                localCuda = component "local_cuda" "Resolves the entrypoint in-process on a CUDA device." "Python: torch (consumer)"
                remoteSsh = component "remote_ssh" "scp + ssh to a node; per-candidate timeout." "Python: ssh/scp CLI"
                hfJobs = component "hf_jobs" "PEP-723 UV job; install spec from RemoteRef.package." "Python: huggingface_hub"
                docker = component "docker" "Not-yet-implemented stub." "Python"
                worker = component "remote_worker" "Node-side runner: imports the entrypoint, runs train_and_evaluate, prints one JSON line." "Python"
                factory = component "create_backend" "Registry: comma-string -> backend(s) -> BackendPool." "Python"

                factory -> pool "Wraps multiple backends"
                pool -> localCuda "Dispatches"
                pool -> remoteSsh "Dispatches"
                pool -> hfJobs "Dispatches"
                localCuda -> base "Uses helpers"
                remoteSsh -> base "Uses helpers"
                hfJobs -> base "Uses helpers"
                pool -> backendPort "Implements the port"
            }

            evolve = container "EvolveStrategy [extra]" "Thin adapter over OpenEvolve: config translation, AST sandbox, seed cache/resume, the evaluator plugin, config-derived RemoteObjective." "Python: ruthless.strategies.evolve_" {
                sandbox = component "sandbox" "AST allow-list validator (ValidationProfile + validate_program), domain-free (ADR-001)." "Python"
                evaluator = component "evaluator" "EvolveEvaluator: OpenEvolve plugin; sandbox gate; single failure->sentinel mapping." "Python"
                evostrategy = component "strategy" "EvolveStrategy.run; _translate_to_openevolve_config; _remote_objective_from_config; seed resume." "Python"

                evostrategy -> sandbox "Validates Level-2 source"
                evostrategy -> evaluator "Builds + drives"
                evaluator -> sandbox "Gates candidate code"
                evaluator -> backendPort "Dispatches via the port"
                evostrategy -> strategyPort "Implements SearchStrategy"
            }

            optuna = container "OptunaStrategy [extra]" "Resumable Bayesian/sampler calibration: wraps an Optuna study (create_study + optimize), warm-start enqueue, ParamSpec->suggest, SQLite resume; uses the CachedObjective fast path." "Python: ruthless.strategies.optuna_" {
                optstrategy = component "strategy" "OptunaStrategy.run: study/resume (load_if_exists + remaining-trials), warm-start, _suggest, best/history from study.trials." "Python"

                optstrategy -> strategyPort "Implements SearchStrategy"
                optstrategy -> objectivePort "Fast path via CachedObjective; else the backend port"
                optstrategy -> guards "Records penalty scores (degenerate trials)"
            }
        }

        user -> random "Constructs and runs (primary API)" "Python"
        user -> evolve "Runs structural search" "Python"
        user -> optuna "Calibrates parameters (Optuna)" "Python"
        user -> cli "Runs a search" "CLI"

        config -> configFile "Reads and parses" "PyYAML safe_load"
        cli -> config "Loads and validates"
        cli -> random "Builds and runs"
        cli -> report "Renders the Result"
        cli -> objective "Resolves a trusted import-string" "importlib + getattr"

        random -> core "Uses ports + value types; checks the scored metric"
        report -> core "Reads the Result value type"

        evolve -> core "Uses ports, value types, error taxonomy"
        evolve -> openevolve "Drives the loop" "run_evolution"
        evolve -> backends "Dispatches candidates" "BackendPool"
        backends -> objective "Evaluates a candidate" "in-process or on a node"
        backends -> node "Ships candidate + runs the entrypoint" "ssh/scp or HF Jobs"
        node -> objective "Imports + runs train_and_evaluate"

        optuna -> core "Uses ports, CachedObjective, errors, guards"
        optuna -> optunalib "Drives the study" "create_study + optimize"
        optuna -> objective "Evaluates a candidate / patch"
    }

    views {
        systemContext res "SystemContext" {
            include *
            autoLayout
        }

        container res "Containers" {
            include *
            autoLayout
        }

        component core "CoreComponents" {
            include *
            autoLayout
        }

        component backends "BackendComponents" {
            include *
            autoLayout
        }

        component evolve "EvolveComponents" {
            include *
            autoLayout
        }

        component optuna "OptunaComponents" {
            include *
            autoLayout
        }

        styles {
            element "Person" {
                shape Person
                background #08427B
                color #ffffff
            }
            element "Software System" {
                background #1168BD
                color #ffffff
            }
            element "External" {
                background #999999
                color #ffffff
            }
            element "Container" {
                background #438DD5
                color #ffffff
            }
            element "Component" {
                background #85BBF0
                color #000000
            }
        }
    }

}
