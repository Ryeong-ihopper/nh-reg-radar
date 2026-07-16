from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yml"
REGRESSION = ROOT / "scripts/db-bootstrap-repeat-up-regression.sh"


def _bootstrap_command() -> str:
    compose = COMPOSE.read_text(encoding="utf-8")
    start = compose.index("  db-bootstrap:")
    end = compose.index("\n  frontend:", start)
    return compose[start:end]


class DatabaseBootstrapRepeatUpTests(unittest.TestCase):
    def test_backend_uses_the_compose_redis_service_for_review_delivery(self) -> None:
        compose = COMPOSE.read_text(encoding="utf-8")
        start = compose.index("  backend:")
        end = compose.index("\n  worker:", start)
        backend = compose[start:end]

        self.assertIn("REDIS_URL: redis://redis:6379/0", backend)
        self.assertIn("REVIEW_QUEUE_NAME:", backend)

    def test_running_volume_guard_precedes_local_postgres_launch(self) -> None:
        command = _bootstrap_command()
        guard = command.index('"$$PGDATA/postmaster.pid"')
        local_launch = command.index("docker-entrypoint.sh postgres &")

        self.assertLess(guard, local_launch)
        self.assertIn('-h postgres -U admin -d "$$POSTGRES_DB"', command)
        self.assertIn("refusing to open an active PostgreSQL data directory", command)
        self.assertIn("reused running postgres service without local server launch", command)

    def test_regression_exercises_fresh_and_repeat_up_with_integrity_checks(self) -> None:
        text = REGRESSION.read_text(encoding="utf-8")

        self.assertEqual(text.count("up -d --wait postgres"), 1)
        self.assertGreaterEqual(text.count("\ncompose_up_postgres\n"), 2)
        self.assertIn("rm --force --stop db-bootstrap", text)
        self.assertIn('"$bootstrap_id" == "$fresh_bootstrap_id"', text)
        self.assertIn('"$postgres_id" != "$fresh_postgres_id"', text)
        self.assertIn("CREATE TABLE g011_repeat_guard", text)
        self.assertIn("repeat_guard_payload", text)
        self.assertIn("database-effective:", text)
        self.assertIn("schema-effective:", text)
        self.assertIn("database-acl:", text)
        self.assertIn("schema-acl:", text)
        self.assertIn('"$fresh_security" != "$repeat_security"', text)
        self.assertIn("PANIC|invalid checkpoint|database system was interrupted", text)
        self.assertIn("down --volumes --remove-orphans", text)

    @unittest.skipUnless(
        os.environ.get("NH_RUN_G011_DOCKER_REGRESSION") == "1",
        "set NH_RUN_G011_DOCKER_REGRESSION=1 for the isolated Docker regression",
    )
    def test_actual_fresh_and_repeat_volume(self) -> None:
        subprocess.run(["bash", str(REGRESSION)], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
