from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from convention_topology.async_orchestration import (
    _build_run_client,
    async_retry_policy_for,
    build_provider_pool,
    run_batch_async,
    run_cell_targeted_async,
    run_main_study_async,
    run_pilot_async,
)
from convention_topology.async_llm import ProviderPool, RateLimitedError
from convention_topology.config import derive_seeds, load_config, resolve_model
from convention_topology.llm import OPENAI_RETRY_EXCEPTIONS, RunFailedError
from convention_topology.orchestration import GridCell
from convention_topology.persistence import META_FIELDS, build_run_id, read_meta, run_paths, write_meta
from convention_topology.run import PROGRAM_CM, PROGRAM_EMERGENCE


def _small_config():
    config = load_config()
    config.params.N = 8
    config.params.total_interactions = 40
    return config


class AsyncRetryPolicyForTests(unittest.TestCase):
    def test_mock_uses_default_retry_on(self):
        model_spec = resolve_model(load_config(), "mock")
        policy = async_retry_policy_for(model_spec)
        self.assertEqual(policy.retry_on, (Exception,))

    def test_real_model_includes_rate_limit_errors(self):
        model_spec = SimpleNamespace(shorthand="llama31")
        policy = async_retry_policy_for(model_spec)
        self.assertIn(RateLimitedError, policy.retry_on)
        for exc in OPENAI_RETRY_EXCEPTIONS:
            self.assertIn(exc, policy.retry_on)


class BuildProviderPoolTests(unittest.TestCase):
    @patch("convention_topology.async_orchestration.AsyncOpenAICompatClient")
    def test_builds_pool_with_rate_limiter(self, mock_client_cls):
        mock_client_cls.return_value = MagicMock(model_id="meta-llama/test")
        model_spec = SimpleNamespace(
            base_url="https://openrouter.ai/api/v1",
            model_id="meta-llama/test",
            api_key_env="TEST_KEY",
            temperature=0.5,
            max_tokens=512,
            openrouter_provider={"only": ["together"]},
            provider="together",
        )
        pool = build_provider_pool(model_spec, api_concurrency=4)
        self.assertIsInstance(pool, ProviderPool)
        self.assertEqual(pool.model_id, "meta-llama/test")
        mock_client_cls.assert_called_once()

    def test_build_run_client_returns_shared_pool_for_real_models(self):
        pool = MagicMock()
        model_spec = SimpleNamespace(shorthand="llama31")
        client = _build_run_client(model_spec, pool, "imitate_modal", 1, ["A", "B"])
        self.assertIs(client, pool)


class RunBatchAsyncTests(unittest.TestCase):
    def test_empty_batch_when_all_cells_already_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            cells = [
                GridCell(PROGRAM_CM, "complete", 1, 1, *derive_seeds(1, "complete", 1, 1)),
            ]
            first = asyncio.run(
                run_batch_async(
                    config, model_spec, cells,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    run_concurrency=2, api_concurrency=0, retry_failed=False,
                )
            )
            second = asyncio.run(
                run_batch_async(
                    config, model_spec, cells,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    run_concurrency=2, api_concurrency=0, retry_failed=False, progress=True,
                )
            )
            self.assertEqual(first, second)
            self.assertTrue(all(status == "completed" for status in second.values()))

    def test_failed_run_only_reattempted_with_retry_failed_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            cell = GridCell(PROGRAM_CM, "complete", 1, 1, *derive_seeds(1, "complete", 1, 1))
            run_id = build_run_id(
                model_spec.shorthand, cell.topology, cell.run_seed, program=PROGRAM_CM, cm_k=cell.cm_k
            )
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, cell.topology, run_id)
            paths.pickle_path.parent.mkdir(parents=True, exist_ok=True)
            paths.events_path.parent.mkdir(parents=True, exist_ok=True)
            fake_meta = {field: None for field in META_FIELDS}
            fake_meta.update(
                run_id=run_id, run_status="failed", topology=cell.topology, cm_k=cell.cm_k, program=PROGRAM_CM,
            )
            write_meta(paths.meta_path, fake_meta)

            no_retry = asyncio.run(
                run_batch_async(
                    config, model_spec, [cell],
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    run_concurrency=1, api_concurrency=0, retry_failed=False,
                )
            )
            self.assertEqual(no_retry[run_id], "failed")

            with_retry = asyncio.run(
                run_batch_async(
                    config, model_spec, [cell],
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    run_concurrency=1, api_concurrency=0, retry_failed=True, progress=True,
                )
            )
            self.assertEqual(with_retry[run_id], "completed")

    @patch("convention_topology.async_orchestration.execute_run_async", new_callable=AsyncMock)
    def test_run_failed_error_is_captured(self, mock_execute):
        mock_execute.side_effect = RunFailedError("exhausted retries")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            cell = GridCell(PROGRAM_EMERGENCE, "complete", 1, 0, *derive_seeds(1, "complete", 0, 1))
            run_id = build_run_id(
                model_spec.shorthand, cell.topology, cell.run_seed, program=PROGRAM_EMERGENCE
            )
            results = asyncio.run(
                run_batch_async(
                    config, model_spec, [cell],
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    run_concurrency=1, api_concurrency=0, retry_failed=False, progress=True,
                )
            )
            self.assertEqual(results[run_id], "failed")

    @patch("convention_topology.async_orchestration.execute_run_async", new_callable=AsyncMock)
    def test_unexpected_exception_is_captured(self, mock_execute):
        mock_execute.side_effect = RuntimeError("boom")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            cell = GridCell(PROGRAM_EMERGENCE, "complete", 1, 0, *derive_seeds(1, "complete", 0, 1))
            run_id = build_run_id(
                model_spec.shorthand, cell.topology, cell.run_seed, program=PROGRAM_EMERGENCE
            )
            results = asyncio.run(
                run_batch_async(
                    config, model_spec, [cell],
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    run_concurrency=1, api_concurrency=0, retry_failed=False,
                )
            )
            self.assertEqual(results[run_id], "failed")


class RunPilotAsyncTests(unittest.TestCase):
    @patch("convention_topology.async_orchestration.run_batch_async", new_callable=AsyncMock)
    def test_topology_filter_passes_subset(self, mock_batch):
        mock_batch.return_value = {}
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        run_pilot_async(
            config, model_spec, program=PROGRAM_EMERGENCE,
            data_dir=Path("/tmp/data"), logs_dir=Path("/tmp/logs"),
            mock_policy="imitate_modal", run_concurrency=2, api_concurrency=0,
            retry_failed=False, topology_filter="complete",
        )
        cells = mock_batch.call_args.args[2]
        self.assertEqual(len(cells), 12)
        self.assertTrue(all(cell.topology == "complete" for cell in cells))


class RunCellTargetedAsyncTests(unittest.TestCase):
    def test_emergence_forced_censoring_stops_at_attempted_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            config.params.max_phase1_interactions = 10
            model_spec = resolve_model(config, "mock")
            semaphore = asyncio.Semaphore(2)
            result = asyncio.run(
                run_cell_targeted_async(
                    config, model_spec, PROGRAM_EMERGENCE, "complete", 0,
                    target=3, attempted_cap=5, shared_pool=None, semaphore=semaphore,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="random",
                    retry_failed=False, progress=True, heartbeat=None,
                )
            )
            self.assertEqual(result["attempted"], 5)
            self.assertEqual(result["eligible"], 0)

    def test_cm_stops_early_once_completed_target_reached(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            semaphore = asyncio.Semaphore(2)
            result = asyncio.run(
                run_cell_targeted_async(
                    config, model_spec, PROGRAM_CM, "complete", 1,
                    target=2, attempted_cap=20, shared_pool=None, semaphore=semaphore,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    retry_failed=False, progress=True, heartbeat=None,
                )
            )
            self.assertEqual(result["eligible"], 2)
            self.assertEqual(result["attempted"], 2)

    def test_resume_skips_precompleted_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            semaphore = asyncio.Semaphore(2)

            first = asyncio.run(
                run_cell_targeted_async(
                    config, model_spec, PROGRAM_CM, "complete", 1,
                    target=2, attempted_cap=20, shared_pool=None, semaphore=semaphore,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    retry_failed=False, progress=False, heartbeat=None,
                )
            )
            second = asyncio.run(
                run_cell_targeted_async(
                    config, model_spec, PROGRAM_CM, "complete", 1,
                    target=2, attempted_cap=20, shared_pool=None, semaphore=semaphore,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    retry_failed=False, progress=True, heartbeat=None,
                )
            )
            self.assertEqual(first["eligible"], 2)
            self.assertEqual(second["eligible"], 2)
            self.assertEqual(second["attempted"], 2)

    def test_targeted_retry_failed_recovers_failed_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            graph_seed, run_seed = derive_seeds(config.run.base_seed, "complete", 1, 1)
            run_id = build_run_id(
                model_spec.shorthand, "complete", run_seed, program=PROGRAM_CM, cm_k=1
            )
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, "complete", run_id)
            paths.pickle_path.parent.mkdir(parents=True, exist_ok=True)
            paths.events_path.parent.mkdir(parents=True, exist_ok=True)
            fake_meta = {field: None for field in META_FIELDS}
            fake_meta.update(
                run_id=run_id, run_status="failed", topology="complete", cm_k=1, program=PROGRAM_CM,
            )
            write_meta(paths.meta_path, fake_meta)

            semaphore = asyncio.Semaphore(1)
            result = asyncio.run(
                run_cell_targeted_async(
                    config, model_spec, PROGRAM_CM, "complete", 1,
                    target=1, attempted_cap=5, shared_pool=None, semaphore=semaphore,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    retry_failed=True, progress=True, heartbeat=None,
                )
            )
            self.assertEqual(result["eligible"], 1)
            statuses = dict(result["runs"])
            self.assertEqual(statuses[run_id], "completed")

    @patch("convention_topology.async_orchestration._run_one_cell", new_callable=AsyncMock)
    def test_targeted_run_failed_error_path(self, mock_run_one):
        mock_run_one.side_effect = RunFailedError("fail")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            semaphore = asyncio.Semaphore(1)
            result = asyncio.run(
                run_cell_targeted_async(
                    config, model_spec, PROGRAM_CM, "complete", 1,
                    target=1, attempted_cap=1, shared_pool=None, semaphore=semaphore,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    retry_failed=False, progress=False, heartbeat=None,
                )
            )
            self.assertEqual(result["eligible"], 0)
            self.assertEqual(result["attempted"], 1)

    @patch("convention_topology.async_orchestration._run_one_cell", new_callable=AsyncMock)
    def test_targeted_unexpected_exception_path(self, mock_run_one):
        mock_run_one.side_effect = ValueError("unexpected")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            semaphore = asyncio.Semaphore(1)
            result = asyncio.run(
                run_cell_targeted_async(
                    config, model_spec, PROGRAM_CM, "complete", 1,
                    target=1, attempted_cap=1, shared_pool=None, semaphore=semaphore,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    retry_failed=False, progress=False, heartbeat=None,
                )
            )
            self.assertEqual(result["eligible"], 0)


class RunMainStudyAsyncTests(unittest.TestCase):
    @patch("convention_topology.async_orchestration.cell_targets")
    def test_main_study_runs_filtered_cells_with_progress(self, mock_targets):
        mock_targets.return_value = [
            {
                "program": PROGRAM_CM,
                "topology": "complete",
                "cm_k": 1,
                "target_min": 2,
                "target_max": 2,
                "attempted_cap": 10,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            results = asyncio.run(
                run_main_study_async(
                    config, model_spec, program=PROGRAM_CM,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                    retry_failed=False, topology_filter="complete",
                    run_concurrency=2, api_concurrency=0, progress=True,
                )
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["topology"], "complete")
            self.assertEqual(results[0]["eligible"], 2)

    @patch("convention_topology.async_orchestration.build_provider_pool")
    @patch("convention_topology.async_orchestration.cell_targets")
    def test_main_study_builds_provider_pool_for_real_models(self, mock_targets, mock_build_pool):
        mock_targets.return_value = [
            {
                "program": PROGRAM_CM,
                "topology": "complete",
                "cm_k": 1,
                "target_min": 1,
                "target_max": 1,
                "attempted_cap": 3,
            }
        ]
        mock_build_pool.return_value = MagicMock()
        config = _small_config()
        model_spec = SimpleNamespace(shorthand="llama31", provider="together")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            with patch("convention_topology.async_orchestration.run_cell_targeted_async", new_callable=AsyncMock) as mock_cell:
                mock_cell.return_value = {
                    "program": PROGRAM_CM, "topology": "complete", "cm_k": 1,
                    "target": 1, "attempted_cap": 3, "attempted": 1, "eligible": 1, "runs": [],
                }
                asyncio.run(
                    run_main_study_async(
                        config, model_spec, program=PROGRAM_CM,
                        data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                        retry_failed=False, run_concurrency=2, api_concurrency=4, progress=False,
                    )
                )
        mock_build_pool.assert_called_once_with(model_spec, api_concurrency=4)


if __name__ == "__main__":
    unittest.main()
