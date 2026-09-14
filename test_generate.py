"""Offline regression tests for catalog repository verification."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import call, patch

from generate import check_manifest, verify_repos


REPO = "https://api.github.com/repos/example/app"
MODERN = f"{REPO}/contents/cloudinabottle.toml"
LEGACY = f"{REPO}/contents/openhost.toml"
FOUND = (200, "{}")
MISSING = (404, "Not Found")
API_ERRORS = (
    (403, "Forbidden"),
    (429, "Too Many Requests"),
    (503, "Service Unavailable"),
    (0, "connection timed out"),
    (401, "Unauthorized"),
)


class CheckManifestTests(unittest.TestCase):
    def test_modern_manifest_takes_precedence(self):
        with patch("generate._github_get", return_value=FOUND) as get:
            self.assertEqual(check_manifest("example/app", "", "test-token"), (True, ""))
        get.assert_called_once_with(MODERN, "test-token")

    def test_legacy_manifest_fallback(self):
        with patch("generate._github_get", side_effect=[MISSING, FOUND]) as get:
            self.assertEqual(check_manifest("example/app", "", "test-token"), (True, ""))
        self.assertEqual(get.call_args_list, [call(MODERN, "test-token"), call(LEGACY, "test-token")])

    def test_no_supported_manifest_fails(self):
        with patch("generate._github_get", side_effect=[MISSING, MISSING]) as get:
            ok, message = check_manifest("example/app", "")
        self.assertFalse(ok)
        self.assertIn("missing manifest", message)
        self.assertIn("cloudinabottle.toml", message)
        self.assertIn("openhost.toml", message)
        self.assertEqual(get.call_args_list, [call(MODERN, ""), call(LEGACY, "")])

    def test_modern_manifest_at_encoded_pinned_ref(self):
        with patch("generate._github_get", return_value=FOUND) as get:
            self.assertEqual(check_manifest("example/app", "release/v1&test#pin"), (True, ""))
        get.assert_called_once_with(MODERN + "?ref=release%2Fv1%26test%23pin", "")

    def test_legacy_manifest_at_pin_is_checked_before_default_branch(self):
        with patch("generate._github_get", side_effect=[MISSING, FOUND]) as get:
            self.assertEqual(check_manifest("example/app", "v1"), (True, ""))
        self.assertEqual(get.call_args_list, [call(MODERN + "?ref=v1", ""), call(LEGACY + "?ref=v1", "")])

    def test_default_branch_manifest_cannot_validate_pin(self):
        for filename, default_responses in (
            ("cloudinabottle.toml", [FOUND]),
            ("openhost.toml", [MISSING, FOUND]),
        ):
            with self.subTest(filename=filename):
                with patch("generate._github_get", side_effect=[MISSING, MISSING, *default_responses]) as get:
                    ok, message = check_manifest("example/app", "v1")
                self.assertFalse(ok)
                self.assertEqual(message, f"{filename} exists on default branch but not at repo_ref 'v1'")
                expected = [call(MODERN + "?ref=v1", ""), call(LEGACY + "?ref=v1", ""), call(MODERN, "")]
                if filename == "openhost.toml":
                    expected.append(call(LEGACY, ""))
                self.assertEqual(get.call_args_list, expected)

    def test_no_manifest_on_pin_or_default_branch_fails(self):
        with patch("generate._github_get", side_effect=[MISSING] * 4) as get:
            ok, message = check_manifest("example/app", "v1")
        self.assertFalse(ok)
        self.assertIn("missing manifest", message)
        self.assertEqual(get.call_count, 4)

    def test_api_errors_skip_instead_of_falling_back_or_reporting_missing(self):
        # Errors at either name, including during default-branch diagnostics,
        # must remain inconclusive rather than treating an unknown file as absent.
        for ref, missing_count in (("", 0), ("", 1), ("v1", 0), ("v1", 1), ("v1", 2), ("v1", 3)):
            for error in API_ERRORS:
                with self.subTest(ref=ref, missing_count=missing_count, status=error[0]):
                    with patch("generate._github_get", side_effect=[MISSING] * missing_count + [error]) as get:
                        ok, message = check_manifest("example/app", ref)
                    self.assertTrue(ok)
                    self.assertIn("manifest not checked", message)
                    self.assertNotIn("missing manifest", message)
                    self.assertEqual(get.call_count, missing_count + 1)


class VerifyReposTests(unittest.TestCase):
    def setUp(self):
        self.feed = {"apps": [{"name": "example", "repo_url": "https://github.com/example/app", "repo_ref": ""}]}
        # Keep the suite independent of local/CI credentials.
        self.env = patch.dict("os.environ", {"GITHUB_TOKEN": "", "GH_TOKEN": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def verify(self, responses, names):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("generate._github_get", side_effect=responses) as get:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = verify_repos(self.feed, names)
        return result, stdout.getvalue(), stderr.getvalue(), get.call_args_list

    def test_public_repo_with_either_manifest_passes_targeted_check(self):
        for manifests in ([FOUND], [MISSING, FOUND]):
            with self.subTest(manifests=manifests):
                result, stdout, stderr, calls = self.verify([(200, '{"private": false}'), *manifests], ["example"])
                self.assertEqual(result, 0)
                self.assertEqual(stdout, "verified 1 repo(s)\n")
                self.assertEqual(stderr, "")
                self.assertEqual(calls[0], call(REPO, ""))

    def test_private_or_missing_repo_fails_without_checking_manifests(self):
        for response in ((200, '{"private": true}'), MISSING):
            for names in (None, ["example"]):
                with self.subTest(response=response, names=names):
                    result, stdout, stderr, calls = self.verify([response], names)
                    self.assertEqual(result, 1)
                    self.assertEqual(stdout, "")
                    self.assertIn("private", stderr)
                    self.assertEqual(calls, [call(REPO, "")])

    def test_missing_manifests_fail_full_and_targeted_checks(self):
        for names in (None, ["example"]):
            with self.subTest(names=names):
                result, stdout, stderr, _ = self.verify([(200, '{"private": false}'), MISSING, MISSING], names)
                self.assertEqual(result, 1)
                self.assertEqual(stdout, "")
                self.assertIn("missing manifest", stderr)

    def test_inconclusive_visibility_warns_on_full_scan_but_fails_targeted(self):
        for response in (*API_ERRORS, (200, "not json")):
            for names in (None, ["example"]):
                with self.subTest(response=response, names=names):
                    result, stdout, stderr, calls = self.verify([response], names)
                    self.assertEqual(result, 1 if names else 0)
                    self.assertIn("warning:", stderr)
                    self.assertEqual(calls, [call(REPO, "")])
                    if names:
                        self.assertIn("could not validate 1 changed repo(s)", stderr)
                    else:
                        self.assertIn("verified 0 repo(s), skipped 1 (not validated)", stdout)

    def test_inconclusive_manifest_warns_on_full_scan_but_fails_targeted(self):
        for missing_count in (0, 1):
            for error in API_ERRORS:
                for names in (None, ["example"]):
                    with self.subTest(missing_count=missing_count, status=error[0], names=names):
                        responses = [(200, '{"private": false}')] + [MISSING] * missing_count + [error]
                        result, stdout, stderr, _ = self.verify(responses, names)
                        self.assertEqual(result, 1 if names else 0)
                        self.assertIn("warning:", stderr)
                        self.assertIn("manifest not checked", stderr)
                        if names:
                            self.assertIn("could not validate 1 changed repo(s)", stderr)
                        else:
                            self.assertIn("verified 0 repo(s), skipped 1 (not validated)", stdout)

    def test_unknown_target_fails_without_network_requests(self):
        result, stdout, stderr, calls = self.verify([], ["unknown"])
        self.assertEqual(result, 1)
        self.assertEqual(stdout, "")
        self.assertIn("no catalog app named: unknown", stderr)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
