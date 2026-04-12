"""
Platform Deployers - Integrations with various deployment platforms
"""
import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from typing import Dict, Optional


def _extract_vercel_deployment_url(stdout: str, stderr: str) -> Optional[str]:
    """
    Parse a deployment URL from Vercel CLI output.
    The CLI prints ``Production: https://....vercel.app`` while progress goes to stderr.
    """
    combined = f"{stdout or ''}\n{stderr or ''}"
    m = re.search(
        r"Production:\s*(https://[^\s\[\]\u00a0]+)",
        combined,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).rstrip(").,]")
    m = re.search(
        r"(https://[a-z0-9][-a-z0-9.]*\.vercel\.app/?)",
        combined,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).rstrip("/")
    lines = [ln.strip() for ln in (stdout or "").strip().splitlines() if ln.strip()]
    if lines and lines[-1].startswith("http"):
        return lines[-1].rstrip("/")
    return None


def sanitize_vercel_project_name(name: str) -> str:
    """
    Vercel project names must be lowercase, <= 100 chars, and may only use
    letters, digits, '.', '_', '-'. No '---' substring.
    Repo slugs like 'Calculator_pro' fail without lowercasing.
    """
    raw = (name or "").strip().lower().removesuffix(".git")
    if not raw:
        return "my-app"
    # Allowed set: a-z 0-9 . _ - ; collapse runs of hyphens (no '---').
    slug = re.sub(r"[^a-z0-9._-]+", "-", raw)
    slug = re.sub(r"-+", "-", slug).strip("-._")
    if not slug:
        return "my-app"
    slug = slug[:100].rstrip("-._") or "my-app"
    return slug


class PlatformDeployer(ABC):
    """Base class for platform deployers"""

    @abstractmethod
    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """Deploy to platform"""
        pass

    def _find_cli(self, *candidates: str) -> Optional[str]:
        """
        Find a CLI executable, checking multiple candidate names.
        On Windows, npm global CLIs are installed as .cmd wrappers
        (e.g. 'vercel.cmd', 'netlify.cmd') which shutil.which('vercel')
        fails to find. Checking both covers all platforms.
        """
        for candidate in candidates:
            path = shutil.which(candidate)
            if path:
                return path
        return None


class VercelDeployer(PlatformDeployer):
    """Deploy to Vercel"""

    @staticmethod
    def _prepare_prebuilt(project_dir: str) -> None:
        """
        Prepare the .vercel/output directory for a --prebuilt deployment.
        This completely bypasses Vercel's build system by creating a
        pre-built output structure. Vercel will serve the files as-is
        without attempting any framework detection or build step.

        Structure created:
          .vercel/output/config.json   -> {"version": 3}
          .vercel/output/static/       -> all project files copied here
        """
        import json

        output_dir = os.path.join(project_dir, ".vercel", "output")
        static_dir = os.path.join(output_dir, "static")
        os.makedirs(static_dir, exist_ok=True)

        # Write the output config
        config_path = os.path.join(output_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump({"version": 3}, f)

        # Copy all project files into static/ (skip .vercel, .git, node_modules)
        skip_dirs = {".vercel", ".git", "node_modules", "__pycache__"}
        for item in os.listdir(project_dir):
            if item in skip_dirs:
                continue
            src = os.path.join(project_dir, item)
            dst = os.path.join(static_dir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Vercel using Vercel CLI.
        - Must be called from the cloned repo directory (PlatformDeployStep handles os.chdir).
        - Requires: npm install -g vercel  AND  vercel login
        """
        try:
            vercel_cmd = self._find_cli("vercel", "vercel.cmd")
            if not vercel_cmd:
                return {
                    "success": False,
                    "error": (
                        "Vercel CLI not found in PATH. "
                        "Install with: npm install -g vercel  "
                        "then login with: vercel login"
                    )
                }

            # Sanity-check the CLI works and is authenticated
            check = subprocess.run(
                [vercel_cmd, "--version"],
                capture_output=True,
                text=True,
                shell=True,
                encoding="utf-8",
                errors="replace",
            )
            if check.returncode != 0:
                return {
                    "success": False,
                    "error": f"Vercel CLI check failed: {check.stderr.strip()}"
                }

            # Prepare the .vercel/output/static structure so we can use --prebuilt.
            # This completely bypasses Vercel's build system and avoids
            # "Unexpected error" during framework auto-detection.
            cwd = os.getcwd()
            self._prepare_prebuilt(cwd)

            # Deploy with --prebuilt: skips build, uploads pre-structured output directly.
            deployment_command = [
                vercel_cmd,
                "deploy",
                "--yes",
                "--prod",
                "--prebuilt",
            ]

            result = subprocess.run(
                deployment_command,
                capture_output=True,
                text=True,
                timeout=300,
                shell=True,
                encoding="utf-8",
                errors="replace",
            )

            deployment_url = _extract_vercel_deployment_url(
                result.stdout or "",
                result.stderr or "",
            )

            if result.returncode == 0:
                url = deployment_url or "https://vercel.com/dashboard"
                return {
                    "success": True,
                    "platform": "Vercel",
                    "deployment_url": url,
                    "message": f"Successfully deployed to {url}",
                }

            # Handle common failures with actionable tips
            err_body = (result.stderr or "").strip() or (result.stdout or "").strip()

            if "not a member of the team" in err_body or "attempted to deploy a commit" in err_body:
                err_body = (
                    "Authentication Error: The logged-in Vercel user does not have "
                    "permission for this project.\n"
                    "Fix: Run 'vercel login' to switch to the correct account, or "
                    "add the user to your Vercel team in the Dashboard."
                )
            elif "Unexpected error" in err_body:
                err_body += (
                    "\nThis usually means Vercel's build system failed. "
                    "A vercel.json was injected but the project may need "
                    "a specific framework configuration."
                )

            if deployment_url:
                err_body = f"{err_body}\n(Last known URL: {deployment_url})"

            return {
                "success": False,
                "error": err_body,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Vercel deployment timed out after 5 minutes"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class NetlifyDeployer(PlatformDeployer):
    """Deploy to Netlify"""

    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Netlify using Netlify CLI.
        - Must be called from the cloned repo directory.
        - Requires: npm install -g netlify-cli  AND  netlify login

        FIX 1: Use _find_cli() to locate 'netlify' or 'netlify.cmd' (Windows).
        FIX 2: Use '.' as deploy dir (CWD) instead of hardcoded './build'.
        FIX 3: Use shell=True on Windows so .cmd wrappers execute correctly.
        """
        try:
            netlify_cmd = self._find_cli("netlify", "netlify.cmd")
            if not netlify_cmd:
                return {
                    "success": False,
                    "error": (
                        "Netlify CLI not found in PATH. "
                        "Install with: npm install -g netlify-cli  "
                        "then login with: netlify login"
                    )
                }

            check = subprocess.run(
                [netlify_cmd, "--version"],
                capture_output=True,
                text=True,
                shell=True
            )
            if check.returncode != 0:
                return {
                    "success": False,
                    "error": f"Netlify CLI check failed: {check.stderr.strip()}"
                }

            site_name = kwargs.get("project_name", kwargs.get("site_name", "my-app"))

            # Deploy CWD; use '.' so it works regardless of build output folder.
            # If the project has a build step, add it here before deploying.
            deployment_command = [
                netlify_cmd, "deploy",
                "--prod",
                f"--site={site_name}",
                "--dir=.",   # Deploy CWD, not a hardcoded ./build
            ]

            result = subprocess.run(
                deployment_command,
                capture_output=True,
                text=True,
                timeout=300,
                shell=True
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "platform": "Netlify",
                    "deployment_url": f"https://{site_name}.netlify.app",
                    "message": "Successfully deployed to Netlify"
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr.strip() or result.stdout.strip()
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Netlify deployment timed out after 5 minutes"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class RailwayDeployer(PlatformDeployer):
    """Deploy to Railway"""

    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Railway (primarily uses GitHub integration — no CLI needed).
        """
        try:
            return {
                "success": True,
                "platform": "Railway",
                "deployment_url": "https://railway.app/project/...",
                "message": "Railway deployment initiated via GitHub integration",
                "instructions": [
                    "1. Connect GitHub repo to Railway",
                    "2. Railway will auto-deploy on push",
                    "3. Visit https://railway.app to manage"
                ]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class HerokuDeployer(PlatformDeployer):
    """Deploy to Heroku"""

    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Heroku using Heroku CLI.
        - Requires: Heroku CLI installed AND heroku login

        FIX: Use _find_cli() to locate 'heroku' or 'heroku.cmd' (Windows).
        """
        try:
            heroku_cmd = self._find_cli("heroku", "heroku.cmd")
            if not heroku_cmd:
                return {
                    "success": False,
                    "error": (
                        "Heroku CLI not found in PATH. "
                        "Install from: https://devcenter.heroku.com/articles/heroku-cli"
                    )
                }

            app_name = kwargs.get("project_name", kwargs.get("app_name", "my-app"))

            # Create Heroku app (may already exist — ignore error)
            subprocess.run(
                [heroku_cmd, "create", app_name],
                capture_output=True,
                text=True,
                shell=True
            )

            # Link remote
            deploy_result = subprocess.run(
                [heroku_cmd, "git:remote", "-a", app_name],
                capture_output=True,
                text=True,
                shell=True
            )

            if deploy_result.returncode == 0:
                return {
                    "success": True,
                    "platform": "Heroku",
                    "deployment_url": f"https://{app_name}.herokuapp.com",
                    "message": "Heroku app linked. Push to deploy: git push heroku main"
                }
            else:
                return {
                    "success": False,
                    "error": deploy_result.stderr.strip()
                }

        except Exception as e:
            return {"success": False, "error": str(e)}


class RenderDeployer(PlatformDeployer):
    """Deploy to Render"""

    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Render (uses GitHub integration — no CLI needed).
        """
        return {
            "success": True,
            "platform": "Render",
            "message": "Render deployment uses GitHub integration",
            "instructions": [
                "1. Go to https://render.com",
                "2. Connect GitHub repository",
                "3. Render will auto-deploy from GitHub",
                "4. Configure build and start commands"
            ]
        }


class FlyDeployer(PlatformDeployer):
    """Deploy to Fly.io"""

    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Fly.io using flyctl.
        - Requires: flyctl installed AND fly auth login

        FIX: Use _find_cli() to locate 'flyctl' or 'flyctl.cmd' (Windows).
        """
        try:
            fly_cmd = self._find_cli("flyctl", "flyctl.cmd", "fly", "fly.cmd")
            if not fly_cmd:
                return {
                    "success": False,
                    "error": (
                        "Fly CLI (flyctl) not found in PATH. "
                        "Install from: https://fly.io/docs/hands-on/install-flyctl/"
                    )
                }

            app_name = kwargs.get("project_name", kwargs.get("app_name", "my-app"))

            launch_result = subprocess.run(
                [fly_cmd, "launch", "--name", app_name, "--now"],
                capture_output=True,
                text=True,
                timeout=300,
                shell=True
            )

            if launch_result.returncode == 0:
                return {
                    "success": True,
                    "platform": "Fly.io",
                    "deployment_url": f"https://{app_name}.fly.dev",
                    "message": "Successfully deployed to Fly.io"
                }
            else:
                return {
                    "success": False,
                    "error": launch_result.stderr.strip() or launch_result.stdout.strip()
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Fly.io deployment timed out after 5 minutes"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Platform deployer factory
class DeployerFactory:
    """Factory to get appropriate deployer for platform"""

    _deployers = {
        "vercel": VercelDeployer,
        "netlify": NetlifyDeployer,
        "railway": RailwayDeployer,
        "heroku": HerokuDeployer,
        "render": RenderDeployer,
        "fly": FlyDeployer,
    }

    @classmethod
    def get_deployer(cls, platform_id: str) -> Optional[PlatformDeployer]:
        """Get deployer instance for platform"""
        deployer_class = cls._deployers.get(platform_id.lower())
        if deployer_class:
            return deployer_class()
        return None

    @classmethod
    def get_supported_platforms(cls) -> list:
        """Get list of supported platform IDs"""
        return list(cls._deployers.keys())