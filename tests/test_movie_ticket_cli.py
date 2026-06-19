from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from direct_ticketing import DirectTicketingError
from movie_ticket_cli import load_purchase_settings
import movie_ticket_cli


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def valid_config() -> dict:
    return {
        "miniProgram": {
            "baseUrl": "https://pandl.xyz",
            "cinemaCode": "34025901",
            "referer": "https://servicewechat.com/wx52420337e5796bd6/15/page-frame.html",
            "distributorId": "",
        },
        "account": {
            "openId": "OPEN-1",
            "memberCardPassword": "TEST-PASSWORD",
        },
        "order": {
            "movieName": "给阿姨的情书",
            "showDate": "2026-06-19",
            "startTime": "14:30",
            "hallName": "2号厅",
            "filmLanguage": "国语",
            "showType": "普通2D",
            "seatNames": ["5排9号"],
            "priceMax": 80,
        },
        "runtime": {"timeout": 20, "outputDir": "picture"},
    }


class ConfigLoadingTests(unittest.TestCase):
    def write_config(self, directory: Path, payload: dict) -> Path:
        path = directory / "config.local.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_loads_nested_config_and_resolves_output_relative_to_config(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            config_path = self.write_config(directory, valid_config())

            settings = load_purchase_settings(config_path, check_only=False)

            self.assertEqual(settings.mini_program.cinema_code, "34025901")
            self.assertEqual(settings.order["openId"], "OPEN-1")
            self.assertEqual(settings.order["seat_positions"], ["5排9号"])
            self.assertEqual(settings.order["ticket_count"], 1)
            self.assertEqual(settings.output_dir, directory / "picture")
            self.assertEqual(settings.member_card, {"password": "TEST-PASSWORD"})

    def test_real_purchase_rejects_placeholder_credentials(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            payload = valid_config()
            payload["account"] = {
                "openId": "本地配置中填写固定值",
                "memberCardPassword": "填写会员卡密码",
            }
            config_path = self.write_config(Path(temporary_directory), payload)

            with self.assertRaisesRegex(DirectTicketingError, "account.openId"):
                load_purchase_settings(config_path, check_only=False)

    def test_check_only_accepts_placeholder_credentials(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            payload = valid_config()
            payload["account"] = {
                "openId": "本地配置中填写固定值",
                "memberCardPassword": "填写会员卡密码",
            }
            config_path = self.write_config(Path(temporary_directory), payload)

            settings = load_purchase_settings(config_path, check_only=True)

            self.assertEqual(settings.order["openId"], "本地配置中填写固定值")
            self.assertEqual(settings.member_card, {"password": "填写会员卡密码"})


class OrchestrationTests(unittest.TestCase):
    def write_config(self, directory: Path) -> Path:
        path = directory / "config.local.json"
        path.write_text(json.dumps(valid_config(), ensure_ascii=False), encoding="utf-8")
        return path

    @patch("movie_ticket_cli.DirectTicketRunner")
    @patch("movie_ticket_cli.CinemaApiClient")
    def test_check_only_queries_without_lock_or_member_payment(self, client_class, runner_class):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = self.write_config(Path(temporary_directory))
            runner_class.return_value.run.return_value = {"success": True, "dry_run": True}

            result = movie_ticket_cli.run_from_config(config_path, check_only=True)

            client_class.assert_called_once_with(
                base_url="https://pandl.xyz",
                cinema_code="34025901",
                headers={
                    "Referer": "https://servicewechat.com/wx52420337e5796bd6/15/page-frame.html"
                },
                timeout=20,
                ticket_picture_dir=Path(temporary_directory) / "picture",
            )
            criteria = runner_class.return_value.run.call_args.args[0]
            self.assertEqual(criteria.open_id, "OPEN-1")
            self.assertEqual(criteria.cinema_code, "34025901")
            runner_class.return_value.run.assert_called_once_with(
                criteria,
                dry_run=True,
                member_card=None,
            )
            self.assertTrue(result["success"])

    @patch("movie_ticket_cli.DirectTicketRunner")
    @patch("movie_ticket_cli.CinemaApiClient")
    def test_default_execution_locks_and_pays_with_configured_password(self, client_class, runner_class):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = self.write_config(Path(temporary_directory))
            runner_class.return_value.run.return_value = {"success": True, "dry_run": False}

            movie_ticket_cli.run_from_config(config_path)

            criteria = runner_class.return_value.run.call_args.args[0]
            runner_class.return_value.run.assert_called_once_with(
                criteria,
                dry_run=False,
                member_card={"password": "TEST-PASSWORD"},
            )

    @patch("movie_ticket_cli.run_from_config")
    def test_main_prints_json_and_forwards_check_only(self, run_from_config):
        run_from_config.return_value = {"success": True, "dry_run": True}
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = movie_ticket_cli.main(
                ["--config", "custom.json", "--check-only"]
            )

        run_from_config.assert_called_once_with(
            Path("custom.json"), check_only=True
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(output.getvalue()),
            {"success": True, "dry_run": True},
        )

    @patch("movie_ticket_cli.run_from_config")
    def test_main_redacts_credentials_and_member_identifiers(self, run_from_config):
        run_from_config.return_value = {
            "success": True,
            "lock_payload": {"openId": "OPEN-SECRET"},
            "trace": [
                {
                    "request_body": {
                        "password": "PWD-SECRET",
                        "cardCode": "CARD-SECRET",
                        "memberPhone": "13800000000",
                    }
                }
            ],
        }
        output = io.StringIO()

        with redirect_stdout(output):
            movie_ticket_cli.main(["--config", "custom.json"])

        rendered = output.getvalue()
        self.assertNotIn("OPEN-SECRET", rendered)
        self.assertNotIn("PWD-SECRET", rendered)
        self.assertNotIn("CARD-SECRET", rendered)
        self.assertNotIn("13800000000", rendered)
        self.assertEqual(rendered.count("[REDACTED]"), 4)


class ProjectStructureTests(unittest.TestCase):
    def test_project_has_cli_entry_and_no_fastapi_entry(self):
        self.assertTrue((PROJECT_ROOT / "movie_ticket_cli.py").exists())
        self.assertTrue((PROJECT_ROOT / "direct_ticketing.py").exists())
        self.assertFalse((PROJECT_ROOT / "backend").exists())
        self.assertFalse((PROJECT_ROOT / "backend/app/main.py").exists())
        self.assertFalse((PROJECT_ROOT / "backend/app/api/ticket.py").exists())
        self.assertFalse((PROJECT_ROOT / "backend/tests/test_ticket_api.py").exists())


if __name__ == "__main__":
    unittest.main()
