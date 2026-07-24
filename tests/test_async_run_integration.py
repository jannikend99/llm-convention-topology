from __future__ import annotations

import asyncio
import random
import tempfile
import unittest
from pathlib import Path

from convention_topology.async_llm import AsyncClientAdapter, AsyncRetryPolicy
from convention_topology.async_orchestration import run_batch_async
from convention_topology.async_run import execute_cm_run_async, execute_emergence_run_async
from convention_topology.async_simulation import make_async_interaction_step
from convention_topology.config import derive_seeds, load_config, resolve_model
from convention_topology.llm import MockLLMClient, RetryPolicy
from convention_topology.networks import get_interaction_network
from convention_topology.orchestration import GridCell, run_batch
from convention_topology.persistence import load_run_pickle, read_meta
from convention_topology.run import (
    PROGRAM_CM,
    PROGRAM_EMERGENCE,
    RunConfig,
    execute_cm_run,
    execute_emergence_run,
)
from convention_topology.simulation import swap_committed


SYNC_FAST_RETRY = RetryPolicy(sleep=lambda _: None)


async def _async_noop_sleep(_s):
    return None


ASYNC_FAST_RETRY = AsyncRetryPolicy(sleep=_async_noop_sleep)

EMERGENCE_OPTIONS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
CM_OPTIONS = ["Q", "M"]


def _emergence_config(**overrides) -> RunConfig:
    base = dict(
        program=PROGRAM_EMERGENCE, model_shorthand="mock", model_id="mock", endpoint_base_url="",
        topology="complete", cm_k=0, graph_seed=0, run_seed=0, config_hash="deadbeefdeadbeef",
        prompt_template_version="v1-ashery-chat-split", code_commit="testcommit",
        options=EMERGENCE_OPTIONS, n=4,
    )
    base.update(overrides)
    return RunConfig(**base)


def _cm_config(**overrides) -> RunConfig:
    base = dict(
        program=PROGRAM_CM, model_shorthand="mock", model_id="mock", endpoint_base_url="",
        topology="complete", cm_k=1, graph_seed=0, run_seed=0, config_hash="deadbeefdeadbeef",
        prompt_template_version="v1-ashery-chat-split", code_commit="testcommit",
        options=CM_OPTIONS, incumbent_index=0, n=4, phase2_horizon=100,
    )
    base.update(overrides)
    return RunConfig(**base)


class AsyncEmergenceRunTests(unittest.TestCase):
    def test_completes_with_full_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _emergence_config()
            client = AsyncClientAdapter(
                MockLLMClient(policy="imitate_modal", rng=random.Random(99), options=list(cfg.options))
            )
            paths = asyncio.run(
                execute_emergence_run_async(
                    cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=ASYNC_FAST_RETRY
                )
            )
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["run_status"], "completed")
            self.assertIsNotNone(meta["t_gate"])


class AsyncSyncEquivalenceTests(unittest.TestCase):
    """Core reproducibility lock: the async engine must produce byte-identical
    trajectories to the sync engine for the same seed and mock policy."""

    def test_emergence_outcomes_identical_across_engines(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _emergence_config(run_seed=7)

            sync_client = MockLLMClient(policy="imitate_modal", rng=random.Random(99), options=list(cfg.options))
            sync_paths = execute_emergence_run(
                cfg, sync_client, data_dir=data_dir / "s", logs_dir=logs_dir / "s", retry_policy=SYNC_FAST_RETRY
            )
            async_client = AsyncClientAdapter(
                MockLLMClient(policy="imitate_modal", rng=random.Random(99), options=list(cfg.options))
            )
            async_paths = asyncio.run(
                execute_emergence_run_async(
                    cfg, async_client, data_dir=data_dir / "a", logs_dir=logs_dir / "a",
                    retry_policy=ASYNC_FAST_RETRY,
                )
            )

            sync_tracker = load_run_pickle(sync_paths.pickle_path)["tracker"]
            async_tracker = load_run_pickle(async_paths.pickle_path)["tracker"]
            self.assertEqual(sync_tracker["outcome"], async_tracker["outcome"])
            self.assertEqual(sync_tracker["answers"], async_tracker["answers"])
            self.assertEqual(sync_tracker["players"], async_tracker["players"])
            self.assertEqual(read_meta(sync_paths.meta_path)["t_gate"], read_meta(async_paths.meta_path)["t_gate"])

    def test_cm_outcomes_identical_across_engines(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _cm_config(cm_k=2, n=8, phase2_horizon=80, run_seed=5)

            sync_client = MockLLMClient(policy="imitate_modal", rng=random.Random(3), options=list(cfg.options))
            sync_paths = execute_cm_run(
                cfg, sync_client, data_dir=data_dir / "s", logs_dir=logs_dir / "s", retry_policy=SYNC_FAST_RETRY
            )
            async_client = AsyncClientAdapter(
                MockLLMClient(policy="imitate_modal", rng=random.Random(3), options=list(cfg.options))
            )
            async_paths = asyncio.run(
                execute_cm_run_async(
                    cfg, async_client, data_dir=data_dir / "a", logs_dir=logs_dir / "a",
                    retry_policy=ASYNC_FAST_RETRY,
                )
            )

            sync_tracker = load_run_pickle(sync_paths.pickle_path)["tracker"]
            async_tracker = load_run_pickle(async_paths.pickle_path)["tracker"]
            self.assertEqual(sync_tracker["outcome"], async_tracker["outcome"])
            self.assertEqual(sync_tracker["answers"], async_tracker["answers"])
            sync_meta, async_meta = read_meta(sync_paths.meta_path), read_meta(async_paths.meta_path)
            self.assertEqual(sync_meta["committed_to"], async_meta["committed_to"])
            self.assertEqual(sync_meta["incumbent_label"], async_meta["incumbent_label"])


class AsyncInteractionStepTests(unittest.TestCase):
    def test_all_committed_phase2_makes_zero_client_calls(self):
        n = 24
        simulation = get_interaction_network("complete", n=n, graph_seed=1)
        rng = random.Random(0)
        swap_committed(simulation, n, rng)
        mock = MockLLMClient(policy="always", rng=random.Random(1), options=["A", "B"], always_label="A")
        client = AsyncClientAdapter(mock)
        step = make_async_interaction_step(
            simulation, client, 5, (-50, 100), ["A", "B"], rng, committed_to="A", retry_policy=ASYNC_FAST_RETRY
        )
        tracker = {"players": [], "answers": [], "outcome": []}

        async def go():
            for _ in range(20):
                await step(tracker)

        asyncio.run(go())
        self.assertEqual(mock.call_count, 0)
        self.assertEqual(len(tracker["outcome"]), 20)


class AsyncBatchEquivalenceTests(unittest.TestCase):
    """Run-level lock: the async batch scheduler must yield the same
    {run_id: status} mapping as the sync `run_batch` for the offline mock, and
    must resume (skip everything) on a second pass. Covers the scheduler's grid,
    skip/resume and status folding — complements the per-run trajectory lock."""

    @staticmethod
    def _cm_cells():
        return [
            GridCell(
                PROGRAM_CM, "complete", i, ((i - 1) % 6) + 1,
                *derive_seeds(1, "complete", ((i - 1) % 6) + 1, i),
            )
            for i in range(1, 7)
        ]

    @staticmethod
    def _small_config():
        config = load_config()
        config.params.N = 8  # >= max cm_k (6)
        config.params.total_interactions = 40  # short CM horizon for the test
        return config

    def test_async_batch_matches_sync_batch_and_resumes(self):
        config = self._small_config()
        model_spec = resolve_model(config, "mock")
        cells = self._cm_cells()

        with tempfile.TemporaryDirectory() as tmp_sync:
            sync_results = run_batch(
                config, model_spec, cells,
                data_dir=Path(tmp_sync) / "data", logs_dir=Path(tmp_sync) / "logs",
                mock_policy="imitate_modal", workers=1, retry_failed=False,
            )

        with tempfile.TemporaryDirectory() as tmp_async:
            data_dir, logs_dir = Path(tmp_async) / "data", Path(tmp_async) / "logs"
            async_results = asyncio.run(
                run_batch_async(
                    config, model_spec, cells,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    run_concurrency=4, api_concurrency=0, retry_failed=False,
                )
            )
            resume_results = asyncio.run(
                run_batch_async(
                    config, model_spec, cells,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    run_concurrency=4, api_concurrency=0, retry_failed=False,
                )
            )

        self.assertEqual(set(async_results.keys()), set(sync_results.keys()))
        self.assertEqual(async_results, sync_results)
        self.assertEqual(resume_results, async_results)  # second pass = all skipped


if __name__ == "__main__":
    unittest.main()
