from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "scripts" / "release-smoke.sh"
RECOVERY = ROOT / "scripts" / "release-recovery-rehearsal.sh"
PROD_COMPOSE = ROOT / "compose.prod.yml"


class ReleaseRecoveryContractTests(unittest.TestCase):
    def test_release_smoke_orders_g011_before_existing_volume_actions(self) -> None:
        text = SMOKE.read_text(encoding="utf-8")

        gate = text.index("run_g011_gate")
        fresh = text.index("run_fresh_start")
        restart = text.index("run_restart_and_outages")
        self.assertLess(gate, fresh)
        self.assertLess(fresh, restart)
        self.assertIn("NH_RUN_G011_DOCKER_REGRESSION=1", text)
        self.assertIn("G011_COLD_GATE_SECONDS", text)
        self.assertIn("G011_REGRESSION_SECONDS", text)
        self.assertIn("G011_FRESH_VOLUME_SECONDS", text)
        self.assertIn('timeout --signal=TERM "$timeout_seconds"', text)
        self.assertIn("G011_FRESH_VOLUME_SECONDS", text)
        self.assertIn("PROD_COLD_START_SECONDS", text)
        self.assertLess(text.index("up -d --wait postgres"), text.index("up -d --wait\n"))
        self.assertIn("--fresh-project", text)
        self.assertIn("--with-restart-and-outages", text)

    def test_release_smoke_has_bounded_health_outage_and_exact_cleanup(self) -> None:
        text = SMOKE.read_text(encoding="utf-8")

        for service in (
            "frontend",
            "backend",
            "worker",
            "postgres",
            "redis",
            "minio",
            "qdrant",
            "opensearch",
        ):
            self.assertIn(service, text)
        self.assertIn("wait_for_service_health", text)
        self.assertIn("wait_for_worker_not_ready", text)
        self.assertIn("down --volumes --remove-orphans", text)
        self.assertIn("label=com.docker.compose.project", text)
        self.assertIn("set +e", text)
        self.assertIn("chmod -R a+rwX /cleanup", text)
        self.assertIn("release backup directory remains", text)
        self.assertIn("release recovery resources remain", text)
        self.assertIn('g011_compose[@]}" down --volumes --remove-orphans', text)
        self.assertIn("G011 resources remain after outer cleanup", text)

    def test_release_smoke_bounds_compose_and_docker_processes_uniformly(self) -> None:
        text = SMOKE.read_text(encoding="utf-8")

        self.assertIn("run_with_timeout()", text)
        self.assertIn("compose_call()", text)
        self.assertIn("g011_compose_call()", text)
        self.assertIn("docker_call()", text)
        self.assertIn("cleanup_compose_call()", text)
        self.assertIn("cleanup_g011_compose_call()", text)
        self.assertIn("cleanup_docker_call()", text)
        for command in (
            "compose_call config --quiet",
            "compose_call build frontend backend worker",
            "compose_call stop frontend backend worker",
            "compose_call up -d --wait frontend backend worker",
            "compose_call stop redis",
            "compose_call start redis",
            'compose_call stop "$service"',
            'compose_call start "$service"',
            "compose_call restart postgres",
            "compose_call exec -T postgres",
        ):
            self.assertIn(command, text)
        self.assertNotRegex(text, r'(?m)^\s*"\$\{compose\[@\]\}"')
        self.assertNotRegex(text, r'(?m)^\s*"\$\{g011_compose\[@\]\}"')

    def test_release_smoke_cleanup_is_repeat_signal_safe_and_preserves_status(self) -> None:
        text = SMOKE.read_text(encoding="utf-8")

        self.assertIn("cleanup_started=false", text)
        self.assertIn("trap - EXIT", text)
        self.assertIn("trap '' INT TERM", text)
        self.assertIn("trap 'handle_signal INT' INT", text)
        self.assertIn("trap 'handle_signal TERM' TERM", text)
        self.assertIn("cleanup_started=true", text)
        self.assertIn("if ((exit_code == 0)); then", text)
        self.assertIn('exit "$exit_code"', text)
        self.assertNotIn("--resume", text)
        self.assertLess(text.index("project_resources \"$project\""), text.index("run_g011_gate\n"))

    def test_recovery_rehearses_lossy_migration_restore_and_durable_stores(self) -> None:
        text = RECOVERY.read_text(encoding="utf-8")

        self.assertIn("alembic upgrade head", text)
        self.assertIn("alembic downgrade base", text)
        self.assertIn("pg_dump", text)
        self.assertIn("pg_restore", text)
        self.assertIn("mc mirror", text)
        self.assertIn("trap cleanup_backup_permissions EXIT", text)
        self.assertIn("/snapshots", text)
        self.assertIn("/snapshots/recover?wait=false", text)
        self.assertIn("file:///qdrant/snapshots/m8-release-backup", text)
        self.assertIn("docker cp", text)
        self.assertIn("qdrant_node_checksum", text)
        self.assertIn("time.monotonic() + 180", text)
        self.assertIn("except (urllib.error.URLError, TimeoutError)", text)
        self.assertIn("failed: 404", text)
        self.assertIn("failed: 503", text)
        self.assertIn('"failed: 500" in error', text)
        self.assertIn('"Local shard 0 not found" in error', text)
        self.assertIn("stop opensearch", text)
        self.assertIn("up -d --wait --wait-timeout 180 opensearch", text)
        self.assertIn("logs --no-color --tail=80 qdrant", text)
        self.assertIn("timeout --signal=TERM 240", text)
        self.assertIn("OPENSEARCH_REINDEXED", text)
        self.assertIn('"redis":"excluded"', text)
        self.assertNotIn("redis.rdb", text)
        self.assertNotIn("dump.rdb", text)
        self.assertIn("sha256sum", text)

    def test_qdrant_async_submission_response_allowlist(self) -> None:
        production = " ".join(RECOVERY.read_text(encoding="utf-8").split())
        backup_outer = production.index(
            'timeout --signal=TERM 240 "${compose[@]}" run --rm --no-deps'
        )
        backup_volume = production.index('--volume "$backup_dir:/backup"', backup_outer)
        snapshot_create = production.index(
            'snapshot = request_json( "POST", '
            'f"{qdrant}/collections/{collection}/snapshots?wait=true", timeout=180, )'
        )
        self.assertLess(backup_outer, backup_volume)
        self.assertLess(backup_volume, snapshot_create)
        self.assertIn(
            'f"{qdrant}/collections/{collection}/snapshots/{snapshot_name}", timeout=30',
            production,
        )
        self.assertIn(
            'submission_accepted = ( restored.get("result") is True or '
            'restored.get("status") == "accepted" )',
            production,
        )
        self.assertIn("if not submission_accepted:", production)
        self.assertIn("time.monotonic() + 180", production)
        self.assertIn('.get("status") != "green"', production)
        self.assertIn("points/4242", production)
        self.assertIn("provider-free-qdrant-restore", production)
        self.assertIn(
            'transient_shard_install = ( "failed: 500" in error and '
            '"Local shard 0 not found" in error )',
            production,
        )
        self.assertIn("and not transient_shard_install", production)

        download = production.index("snapshot_path.write_bytes(response.read())")
        waited_delete = production.index(
            'request_json("DELETE", f"{qdrant}/collections/{collection}?wait=true")',
            download,
        )
        deleted = production.index("QDRANT_SOURCE_COLLECTION_DELETED", waited_delete)
        node_copy = production.index("docker cp")
        recover = production.index("/snapshots/recover?wait=false")
        self.assertLess(snapshot_create, download)
        self.assertLess(download, waited_delete)
        self.assertLess(waited_delete, deleted)
        self.assertLess(deleted, node_copy)
        self.assertLess(node_copy, recover)
        self.assertIn(
            'request_json("DELETE", f"{qdrant}/collections/{collection}?wait=true")',
            production,
        )
        self.assertEqual(
            production.count(
                'request_json("DELETE", f"{qdrant}/collections/{collection}?wait=true")'
            ),
            2,
        )
        self.assertEqual(production.count("QDRANT_SOURCE_COLLECTION_DELETED"), 1)
        self.assertNotIn(
            "file:///qdrant/snapshots/{collection}/m8-release-backup.snapshot",
            production,
        )
        restore_helper = production[production.index("M8 Qdrant restore:") :]
        self.assertNotIn(
            'request_json("DELETE", f"{qdrant}/collections/{collection}',
            restore_helper,
        )

        def accepted(response: dict[str, object]) -> bool:
            return response.get("result") is True or response.get("status") == "accepted"

        for response in ({"result": True}, {"status": "accepted", "time": 0.001}):
            self.assertTrue(accepted(response))
        for response in (
            {},
            {"result": False},
            {"result": 1},
            {"status": "ok"},
            {"status": True},
            {"result": False, "status": "rejected"},
        ):
            self.assertFalse(accepted(response))

        def transient_shard_install(error: str) -> bool:
            return "failed: 500" in error and "Local shard 0 not found" in error

        self.assertTrue(
            transient_shard_install(
                "GET failed: 500 Service internal error: Local shard 0 not found"
            )
        )
        for error in (
            "GET failed: 500 Service internal error",
            "GET failed: 500 Local shard 1 not found",
            "GET failed: 500 Local shard 0 unavailable",
            "GET failed: 500 resource not found",
            "GET failed: 404 Local shard 0 not found",
        ):
            self.assertFalse(transient_shard_install(error))

    def test_prod_override_declares_graceful_stop_windows(self) -> None:
        text = PROD_COMPOSE.read_text(encoding="utf-8")

        self.assertGreaterEqual(text.count("stop_grace_period:"), 3)
        for service in ("frontend", "backend", "worker"):
            section = re.search(rf"(?ms)^  {service}:\n(?P<body>.*?)(?=^  [a-z].*:\n|\Z)", text)
            self.assertIsNotNone(section)
            self.assertIn("stop_grace_period:", section.group("body"))  # type: ignore[union-attr]

    @unittest.skipUnless(
        os.environ.get("NH_RUN_M8_RELEASE_DOCKER") == "1",
        "set NH_RUN_M8_RELEASE_DOCKER=1 for the isolated production recovery smoke",
    )
    def test_actual_release_recovery_smoke(self) -> None:
        subprocess.run(
            [
                "bash",
                str(SMOKE),
                "--env-file",
                str(ROOT / ".env.prod.example"),
                "--fresh-project",
                "--with-restart-and-outages",
            ],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
