"""server.json is the project's entry in the official MCP Registry (registry.modelcontextprotocol.io).

The registry refuses a publication whose version was published before, checks the PyPI package's README for the
`mcp-name:` line, and caps the description at 100 characters. These keep the file true at every release cut.
"""
import json
import pathlib
import re
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER = json.loads((ROOT / "server.json").read_text())
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]


class ServerJson(unittest.TestCase):
    def test_versions_follow_the_package(self):
        """A release cut that bumps pyproject.toml and forgets server.json would publish the old version again."""
        self.assertEqual(SERVER["version"], PROJECT["version"])
        self.assertEqual([p["version"] for p in SERVER["packages"]], [PROJECT["version"]])

    def test_package_is_this_project_started_by_its_own_script(self):
        (pkg,) = SERVER["packages"]
        self.assertEqual((pkg["registryType"], pkg["identifier"]), ("pypi", PROJECT["name"]))
        self.assertEqual(pkg["transport"], {"type": "stdio"})
        # `uvx <identifier>` runs the console script of that name.
        self.assertEqual(PROJECT["scripts"][PROJECT["name"]], "harness.mcp_server:main")

    def test_readme_carries_the_ownership_line(self):
        """PyPI shows the README; the registry looks there for `mcp-name: <name>` followed by a boundary."""
        self.assertEqual(PROJECT["readme"], "README.md")
        self.assertRegex((ROOT / "README.md").read_text(), r"mcp-name: " + re.escape(SERVER["name"]) + r"(\s|-->)")

    def test_the_registry_limits(self):
        self.assertRegex(SERVER["name"], r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")
        self.assertLessEqual(len(SERVER["description"]), 100)
        self.assertLessEqual(len(SERVER["title"]), 100)

    def test_arguments_and_variables_exist_in_the_server(self):
        """Every flag and variable the entry advertises is one the server reads."""
        (pkg,) = SERVER["packages"]
        source = "".join(p.read_text() for p in (ROOT / "harness").glob("*.py"))
        for arg in pkg["packageArguments"]:
            self.assertIn(f'"{arg["name"]}"', source)
        for var in pkg["environmentVariables"]:
            self.assertIn(var["name"], source)

    def test_the_repository_is_the_gitlab_one(self):
        self.assertEqual(SERVER["repository"]["source"], "gitlab")
        self.assertEqual(SERVER["repository"]["url"], PROJECT["urls"]["Repository"])


if __name__ == "__main__":
    unittest.main()
