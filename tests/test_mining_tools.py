import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from mining_tools import HashrateChart, SessionStats, redact_log, validate_settings


class MiningToolsTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.clock = lambda: self.now
        self.config = dict(
            pool="pool.example:3333",
            user="wallet-secret",
            password="password-secret",
            threads="0",
            donate="0",
            args="",
        )

    def test_session_lifecycle(self):
        stats = SessionStats(self.clock)
        self.assertEqual(stats.snapshot()["runtime"], 0)
        stats.start()
        stats.add_speed(10)
        self.now = 30
        stats.add_speed(30)
        stats.update_shares(9, 1)
        stats.update_shares(18, 2)
        self.assertEqual(
            stats.snapshot(),
            dict(runtime=30, average=20, accepted=18, rejected=2, rejection_ratio=0.1),
        )
        stats.stop()
        self.now = 90
        stats.stop()
        stats.add_speed(100)
        self.assertEqual(stats.snapshot()["runtime"], 30)
        self.assertEqual(stats.snapshot()["average"], 20)
        stats.reset()
        self.assertEqual(stats.snapshot()["average"], 0)
        self.assertEqual(stats.snapshot()["accepted"], 0)
        self.assertEqual(stats.snapshot()["rejection_ratio"], 0)

    def test_bad_stats_inputs(self):
        stats = SessionStats(self.clock)
        stats.start()
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                stats.add_speed(value)
        for counts in ((-1, 0), (1, 0.5), (True, 0)):
            with self.assertRaises(ValueError):
                stats.update_shares(*counts)

    def test_pool_formats(self):
        for pool in (
            "example.org:3333",
            "[::1]:4444",
            "stratum+tcp://example.org:3333",
            "stratum+ssl://[2001:db8::1]:443",
        ):
            self.assertEqual(validate_settings(dict(self.config, pool=pool)), {})
        for pool in (
            "",
            "host",
            "host:0",
            "host:65536",
            "::1:3333",
            "http://host:3333",
            "host:no",
            "host:33/path",
            "bad host:33",
        ):
            self.assertIn("pool", validate_settings(dict(self.config, pool=pool)))

    def test_validation_limits_and_args(self):
        for field, values in (
            ("threads", ("-1", "1.2", "2147483648", "")),
            ("donate", ("-1", "101", "nan")),
        ):
            for value in values:
                self.assertIn(
                    field, validate_settings(dict(self.config, **{field: value}))
                )
        self.assertEqual(
            validate_settings(
                dict(
                    self.config,
                    threads="2147483647",
                    donate="100",
                    args='--future-option "some value" positional',
                )
            ),
            {},
        )
        self.assertIn("args", validate_settings(dict(self.config, args="'broken")))
        self.assertIn("user", validate_settings(dict(self.config, user=" ")))
        self.assertEqual(
            validate_settings(dict(self.config, pool="", user="", default_args=True)),
            {},
        )

    def test_redaction_config_and_unknown_args(self):
        config = dict(
            self.config, args='--custom="private token" --other=hidden plain-secret'
        )
        text = "pool.example:3333 wallet-secret password-secret private token hidden plain-secret"
        for configs in (config, [config], {"profile": config}):
            result = redact_log(text, configs)
            for secret in text.split():
                self.assertNotIn(secret, result)
        result = redact_log("broken-secret", [dict(args="'broken-secret")])
        self.assertNotIn("broken-secret", result)

    def test_redaction_common_flags_and_wallets(self):
        text = '--user="unknown wallet" -u other --pass secret -p=another --url host:33 -o ssl:44'
        result = redact_log(text, [])
        for secret in (
            "unknown wallet",
            "other",
            "secret",
            "another",
            "host:33",
            "ssl:44",
        ):
            self.assertNotIn(secret, result)
        for length in (95, 106):
            wallet = "4" + "A" * (length - 1)
            self.assertEqual(redact_log(wallet, []), "[REDACTED]")
        self.assertEqual(
            redact_log("accepted 12 speed 42 H/s", []), "accepted 12 speed 42 H/s"
        )

    def test_chart_bounded_and_paints(self):
        app = QApplication.instance() or QApplication([])
        chart = HashrateChart(max_samples=3, clock=self.clock)
        for stamp, speed in ((0, 0), (1, 10), (60, 20), (180, 5)):
            self.now = stamp
            chart.add_sample(speed)
        self.assertEqual(list(chart.history), [(1, 10), (60, 20), (180, 5)])
        self.assertGreaterEqual(chart.minimumHeight(), 120)
        chart.resize(400, 160)
        self.assertFalse(chart.grab().isNull())
        chart.clear()
        self.assertEqual(len(chart.history), 0)
        self.assertFalse(chart.grab().isNull())
        chart.add_sample(0)
        self.assertFalse(chart.grab().isNull())
        with self.assertRaises(ValueError):
            chart.add_sample(float("nan"))
        chart.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
