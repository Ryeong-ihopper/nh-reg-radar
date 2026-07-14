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
        self.assertIn("PROD_COLD_START_SECONDS", text)
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
        self.assertIn("release recovery resources remain", text)

    def test_recovery_rehearses_lossy_migration_restore_and_durable_stores(self) -> None:
        text = RECOVERY.read_text(encoding="utf-8")

        self.assertIn("alembic upgrade head", text)
        self.assertIn("alembic downgrade base", text)
        self.assertIn("pg_dump", text)
        self.assertIn("pg_restore", text)
        self.assertIn("mc mirror", text)
        self.assertIn("/snapshots", text)
        self.assertIn("snapshots/upload?priority=snapshot", text)
        self.assertIn("OPENSEARCH_REINDEXED", text)
        self.assertIn('"redis":"excluded"', text)
        self.assertNotIn("redis.rdb", text)
        self.assertNotIn("dump.rdb", text)
        self.assertIn("sha256sum", text)

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
