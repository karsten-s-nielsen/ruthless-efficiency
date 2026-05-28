# Structurizr DSL
workspace "ruthless-efficiency" "A general optimisation/search substrate: a pure hexagonal core + pluggable search strategies + pluggable compute backends (Phase 1A)." {

    model {
        user = person "Optimisation User" "A developer who writes an Objective and a search config, then runs a search programmatically or via the CLI."

        objective = softwareSystem "User Objective" "Consumer-supplied evaluation function: a Candidate (params) maps to Metrics. The only thing a consumer must implement." "External"

        configFile = softwareSystem "Config File" "A YAML file declaring the seed, strategy, and parameter space." "External"

        res = softwareSystem "ruthless-efficiency" "Optimisation/search substrate. Phase 1A: pure core + RandomSearchStrategy + in-process backend." {

            cli = container "CLI" "Config-driven entry point. Loads config, resolves a trusted objective import-string, builds the strategy, runs it, prints the report." "Python: ruthless.cli"

            config = container "Config" "Layered Pydantic config with a discriminated strategy union and a discriminated param-space union (float/int/choice, log flag)." "Python: pydantic v2, pyyaml"

            random = container "RandomSearchStrategy" "Built-in search strategy. Samples each parameter per its spec via a seeded numpy RNG, validates only the scored metric, tracks best + history. Drives the determinism gate." "Python: ruthless.strategies.random_"

            report = container "Reporting" "Renders a Result to machine JSON and a human Markdown summary." "Python: ruthless.report"

            core = container "Core & Ports" "The pure hexagon: ports, value types, error taxonomy, penalty guards, parallel map, namespaced logging, and the in-process backend." "Python: ruthless" {
                errors = component "errors" "Error taxonomy: OptimizationError, Fatal/Transient evaluation errors, and classify_metric (scored-metric finiteness)." "Python"
                result = component "result" "Value types: hashable Candidate, Evaluation, Result, and the Metrics alias." "Python"
                objectivePort = component "objective (port)" "The Objective Protocol — the consumer's evaluation contract." "Python Protocol"
                backend = component "backend" "ComputeBackend port + InProcessBackend. Returns the objective's metrics verbatim; timeout is on the port." "Python"
                strategyPort = component "strategy (port)" "Direction enum + the SearchStrategy Protocol." "Python Protocol"
                guards = component "guards" "penalty_metrics — recorded, deliberately-bad scores for degenerate-but-valid candidates." "Python"
                parallel = component "parallel" "map_work_units — optional intra-objective thread/process map." "Python"
                logging = component "logging" "get_logger — namespaced ruthless.* loggers; never configures handlers." "Python"

                objectivePort -> result "Uses Candidate / Metrics"
                backend -> objectivePort "Typed against the objective port"
                backend -> result "Returns Metrics"
                strategyPort -> backend "Typed against the backend port"
                strategyPort -> objectivePort "Typed against the objective port"
                strategyPort -> result "Returns a Result"
                guards -> result "Builds penalty Metrics"
                guards -> strategyPort "Uses Direction"
                errors -> result "References the Metrics scale"
            }
        }

        user -> random "Constructs and runs (primary API)" "Python"
        user -> cli "Runs a search" "CLI: ruthless --config --objective"

        config -> configFile "Reads and parses" "PyYAML safe_load"
        cli -> config "Loads and validates"
        cli -> random "Builds and runs"
        cli -> backend "Dispatches evaluations" "InProcessBackend"
        cli -> report "Renders the Result"
        cli -> objective "Resolves a trusted import-string" "importlib + getattr"

        random -> config "Reads RandomConfig and the param space"
        random -> strategyPort "Implements the SearchStrategy port"
        random -> backend "Dispatches each candidate"
        random -> errors "Validates the scored metric"
        random -> result "Builds Candidate / Evaluation / Result"
        backend -> objective "Evaluates a candidate" "evaluate(candidate)"
        report -> result "Reads the Result value type"
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
