"""
GitHub Repository Analyzer
Detects project type and suggests compatible deployment platforms.
"""
import base64
import json
import logging
import os
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_GITHUB_TOKEN: Optional[str] = os.environ.get("GITHUB_TOKEN")
_GITHUB_HEADERS: Dict[str, str] = {
    "Accept": "application/vnd.github+json",
    **({"Authorization": f"Bearer {_GITHUB_TOKEN}"} if _GITHUB_TOKEN else {}),
}

_API_TIMEOUT = 10  # seconds


class GitHubAnalyzer:
    """Analyzes GitHub repositories to detect project type and compatible platforms."""

    @staticmethod
    def parse_github_url(url: str) -> Dict[str, str]:
        """
        Extract owner and repo name from any common GitHub URL format.
        Supports https, http, .git suffix, /tree/branch subpaths, and SSH URLs.
        """
        url = url.strip().rstrip("/")

        if url.startswith("git@github.com:"):
            path = url[len("git@github.com:"):]
        else:
            parsed = urlparse(url)
            if parsed.netloc not in ("github.com", "www.github.com"):
                raise ValueError(f"Not a GitHub URL: {url!r}")
            path = parsed.path.lstrip("/")

        path = path.removesuffix(".git")
        parts = path.split("/")

        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError(
                f"Cannot extract owner/repo from URL: {url!r}. "
                "Expected format: https://github.com/owner/repo"
            )

        return {"owner": parts[0], "repo": parts[1]}

    @staticmethod
    def _get(url: str) -> Optional[requests.Response]:
        """GET request with shared headers and timeout. Returns None on non-200."""
        try:
            resp = requests.get(url, headers=_GITHUB_HEADERS, timeout=_API_TIMEOUT)
            if resp.status_code == 200:
                return resp
            logger.warning("GitHub API returned %d for %s", resp.status_code, url)
            return None
        except requests.RequestException as exc:
            logger.warning("GitHub API request failed for %s: %s", url, exc)
            return None

    @staticmethod
    def _decode_github_file(api_url: str) -> Optional[str]:
        """Fetch and base64-decode a file from the GitHub contents API."""
        resp = GitHubAnalyzer._get(api_url)
        if resp is None:
            return None
        try:
            data = resp.json()
            return base64.b64decode(data["content"]).decode("utf-8")
        except (KeyError, ValueError) as exc:
            logger.warning("Failed to decode file from %s: %s", api_url, exc)
            return None

    # -----------------------------------------------------------------------
    # FIX: pyproject.toml framework detection added alongside requirements.txt
    # -----------------------------------------------------------------------

    @staticmethod
    def _detect_python_framework(base_url: str, file_names: list) -> Optional[str]:
        """
        Detect Python framework by reading requirements.txt and/or pyproject.toml.

        Checks in order:
        1. requirements.txt  — plain text, check for package names
        2. pyproject.toml    — TOML format, check [project].dependencies
                               and [tool.poetry].dependencies sections
        """
        FRAMEWORK_KEYWORDS = {
            "django":  "django",
            "flask":   "flask",
            "fastapi": "fastapi",
            "tornado": "tornado",
            "aiohttp": "aiohttp",
            "starlette": "starlette",
        }

        # --- requirements.txt ---
        if "requirements.txt" in file_names:
            content = GitHubAnalyzer._decode_github_file(f"{base_url}/requirements.txt")
            if content:
                lower = content.lower()
                for keyword, framework in FRAMEWORK_KEYWORDS.items():
                    if keyword in lower:
                        return framework

        # --- pyproject.toml ---
        # FIX: added pyproject.toml parsing so projects like FastAPI itself
        # (which uses pyproject.toml instead of requirements.txt) are detected.
        if "pyproject.toml" in file_names:
            content = GitHubAnalyzer._decode_github_file(f"{base_url}/pyproject.toml")
            if content:
                lower = content.lower()

                # First try: simple keyword scan (works for both PEP 517 and Poetry)
                for keyword, framework in FRAMEWORK_KEYWORDS.items():
                    if keyword in lower:
                        return framework

                # Second try: parse as TOML for more accurate dependency extraction
                # (Python 3.11+ has tomllib built-in; fall back to keyword scan if unavailable)
                try:
                    try:
                        import tomllib  # Python 3.11+
                    except ImportError:
                        try:
                            import tomli as tomllib  # pip install tomli for <3.11
                        except ImportError:
                            tomllib = None  # type: ignore

                    if tomllib is not None:
                        data = tomllib.loads(content)

                        # PEP 517 style: [project] dependencies = ["fastapi>=0.x"]
                        pep517_deps = data.get("project", {}).get("dependencies", [])

                        # Poetry style: [tool.poetry.dependencies] fastapi = "^0.x"
                        poetry_deps = (
                            data.get("tool", {})
                            .get("poetry", {})
                            .get("dependencies", {})
                        )
                        poetry_dev_deps = (
                            data.get("tool", {})
                            .get("poetry", {})
                            .get("dev-dependencies", {})
                        )

                        all_dep_names = (
                            # PEP 517 deps are strings like "fastapi>=0.100"
                            [d.split("[")[0].split(">=")[0].split("==")[0]
                             .split("!=")[0].split("<")[0].strip().lower()
                             for d in pep517_deps]
                            # Poetry deps are dict keys
                            + [k.lower() for k in poetry_deps]
                            + [k.lower() for k in poetry_dev_deps]
                        )

                        for keyword, framework in FRAMEWORK_KEYWORDS.items():
                            if keyword in all_dep_names:
                                return framework

                except Exception as exc:
                    logger.debug("TOML parse failed, using keyword scan: %s", exc)

        return None

    @staticmethod
    def detect_project_type(owner: str, repo: str) -> Dict:
        """
        Detect project type by inspecting repository root files via GitHub API.
        Always returns a dict with at least: detected_type, framework, runtime.
        """
        base_url = f"https://api.github.com/repos/{owner}/{repo}/contents"

        project_info: Dict = {
            "detected_type": "unknown",
            "framework": None,
            "runtime": None,
            "build_tool": None,
            "has_dockerfile": False,
            "files_found": [],
            "error": None,
        }

        resp = GitHubAnalyzer._get(base_url)
        if resp is None:
            project_info["error"] = "Cannot access repository (check URL and visibility)"
            return project_info

        try:
            files = resp.json()
        except ValueError:
            project_info["error"] = "Invalid response from GitHub API"
            return project_info

        file_names = [
            f["name"] for f in files
            if isinstance(f, dict) and f.get("type") == "file"
        ]
        project_info["files_found"] = file_names

        # --- Node.js / JavaScript ---
        if "package.json" in file_names:
            project_info["runtime"] = "node"
            project_info["detected_type"] = "nodejs"

            content = GitHubAnalyzer._decode_github_file(f"{base_url}/package.json")
            if content:
                try:
                    package_data = json.loads(content)
                    deps = {
                        **package_data.get("dependencies", {}),
                        **package_data.get("devDependencies", {}),
                    }
                    if "next" in deps:
                        project_info["framework"] = "nextjs"
                    elif "nuxt" in deps:
                        project_info["framework"] = "nuxt"
                    elif "react" in deps:
                        project_info["framework"] = "react"
                    elif "vue" in deps:
                        project_info["framework"] = "vue"
                    elif "@angular/core" in deps:
                        project_info["framework"] = "angular"
                    elif "express" in deps:
                        project_info["framework"] = "express"
                except (json.JSONDecodeError, AttributeError) as exc:
                    logger.warning("Could not parse package.json: %s", exc)

        # --- Python ---
        # FIX: now checks requirements.txt OR setup.py OR pyproject.toml,
        # and calls _detect_python_framework() which handles both file types.
        elif any(f in file_names for f in ("requirements.txt", "setup.py", "pyproject.toml")):
            project_info["runtime"] = "python"
            project_info["detected_type"] = "python"
            project_info["framework"] = GitHubAnalyzer._detect_python_framework(
                base_url, file_names
            )

        # --- Static ---
        elif "index.html" in file_names:
            project_info["detected_type"] = "static"
            project_info["runtime"] = "static"
            if any(f.endswith((".jsx", ".tsx")) for f in file_names):
                project_info["framework"] = "react-static"

        # --- Go ---
        elif "go.mod" in file_names or "go.sum" in file_names:
            project_info["runtime"] = "go"
            project_info["detected_type"] = "go"

        # --- Java / Maven ---
        elif "pom.xml" in file_names:
            project_info["runtime"] = "java"
            project_info["detected_type"] = "java"
            project_info["build_tool"] = "maven"

        # --- Ruby ---
        elif "Gemfile" in file_names:
            project_info["runtime"] = "ruby"
            project_info["detected_type"] = "ruby"
            if "config.ru" in file_names:
                project_info["framework"] = "rails"

        # --- Rust ---
        elif "Cargo.toml" in file_names:
            project_info["runtime"] = "rust"
            project_info["detected_type"] = "rust"

        # --- PHP ---
        elif "composer.json" in file_names:
            project_info["runtime"] = "php"
            project_info["detected_type"] = "php"

        # Dockerfile is independent of language
        if "Dockerfile" in file_names:
            project_info["has_dockerfile"] = True

        return project_info

    @staticmethod
    def get_compatible_platforms(project_info: Dict) -> List[Dict]:
        """Return compatible deployment platforms based on detected project type."""
        detected_type = project_info.get("detected_type", "unknown")
        framework = project_info.get("framework")
        has_dockerfile = project_info.get("has_dockerfile", False)

        platforms = []

        if detected_type in ("nodejs", "static") or framework in (
            "nextjs", "react", "vue", "nuxt", "angular"
        ):
            platforms.append({
                "name": "Vercel",
                "id": "vercel",
                "description": "Best for Next.js, React, Vue, and static sites",
                "free_tier": True,
                "deployment_time": "~2 min",
                "features": ["Auto HTTPS", "CDN", "Serverless Functions"],
                "recommended": framework == "nextjs",
            })

        if detected_type in ("nodejs", "static"):
            platforms.append({
                "name": "Netlify",
                "id": "netlify",
                "description": "Perfect for static sites and JAMstack apps",
                "free_tier": True,
                "deployment_time": "~2 min",
                "features": ["Forms", "Functions", "CDN", "Split Testing"],
                "recommended": detected_type == "static",
            })

        if detected_type in ("nodejs", "python", "go", "ruby", "rust"):
            platforms.append({
                "name": "Railway",
                "id": "railway",
                "description": "Easy deployment for any backend service",
                "free_tier": True,
                "deployment_time": "~3 min",
                "features": ["Databases", "Cron Jobs", "Private Networking"],
                "recommended": framework in ("express", "fastapi", "flask", "django"),
            })

        if detected_type in ("nodejs", "python", "ruby", "java", "php", "go"):
            platforms.append({
                "name": "Heroku",
                "id": "heroku",
                "description": "Classic PaaS, supports many languages",
                "free_tier": False,
                "deployment_time": "~4 min",
                "features": ["Add-ons", "Dyno Management", "CI/CD"],
                "recommended": False,
            })

        if detected_type in ("nodejs", "python", "ruby", "go", "rust", "static"):
            platforms.append({
                "name": "Render",
                "id": "render",
                "description": "Modern cloud platform, Heroku alternative",
                "free_tier": True,
                "deployment_time": "~3 min",
                "features": ["Auto Deploy", "Free SSL", "DDoS Protection"],
                "recommended": False,
            })

        if has_dockerfile or detected_type in ("nodejs", "python", "go", "ruby"):
            platforms.append({
                "name": "Fly.io",
                "id": "fly",
                "description": "Run apps close to users worldwide",
                "free_tier": True,
                "deployment_time": "~3 min",
                "features": ["Edge Deployment", "Global Network", "Auto Scaling"],
                "recommended": has_dockerfile,
            })

        if detected_type in ("static", "nodejs"):
            platforms.append({
                "name": "Cloudflare Pages",
                "id": "cloudflare",
                "description": "Fast static site hosting on Cloudflare network",
                "free_tier": True,
                "deployment_time": "~2 min",
                "features": ["Unlimited Bandwidth", "CDN", "Web Analytics"],
                "recommended": False,
            })

        if detected_type in ("nodejs", "python", "go", "php", "ruby", "static"):
            platforms.append({
                "name": "DigitalOcean App Platform",
                "id": "digitalocean",
                "description": "Simple deployment on DigitalOcean",
                "free_tier": True,
                "deployment_time": "~4 min",
                "features": ["Managed Databases", "Auto Scaling", "Load Balancing"],
                "recommended": False,
            })

        if not platforms or has_dockerfile:
            platforms.append({
                "name": "Docker (Generic)",
                "id": "docker",
                "description": "Deploy as Docker container to any platform",
                "free_tier": None,
                "deployment_time": "Varies",
                "features": ["Portable", "Consistent", "Works Anywhere"],
                "recommended": has_dockerfile and not platforms,
            })

        return platforms

    @staticmethod
    def analyze_repository(github_url: str) -> Dict:
        """
        Main entry point — parse URL, detect project type, return platforms.
        """
        try:
            parsed = GitHubAnalyzer.parse_github_url(github_url)
            owner, repo = parsed["owner"], parsed["repo"]

            project_info = GitHubAnalyzer.detect_project_type(owner, repo)

            if project_info.get("error"):
                return {
                    "error": project_info["error"],
                    "analysis_success": False,
                    "compatible_platforms": [],
                }

            platforms = GitHubAnalyzer.get_compatible_platforms(project_info)

            return {
                "repository": f"{owner}/{repo}",
                "github_url": github_url,
                "project_type": project_info.get("detected_type"),
                "framework": project_info.get("framework"),
                "runtime": project_info.get("runtime"),
                "compatible_platforms": platforms,
                "analysis_success": True,
            }

        except ValueError as exc:
            return {
                "error": str(exc),
                "analysis_success": False,
                "compatible_platforms": [],
            }
        except Exception as exc:
            logger.error("Unexpected error analysing %s: %s", github_url, exc, exc_info=True)
            return {
                "error": f"Unexpected error: {exc}",
                "analysis_success": False,
                "compatible_platforms": [],
            }