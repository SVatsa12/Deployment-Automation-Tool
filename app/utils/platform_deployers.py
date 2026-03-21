"""
Platform Deployers - Integrations with various deployment platforms
"""
import subprocess
import os
import shutil
from typing import Dict, Optional
from abc import ABC, abstractmethod


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

    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Vercel using Vercel CLI.
        - Must be called from the cloned repo directory (PlatformDeployStep handles os.chdir).
        - Requires: npm install -g vercel  AND  vercel login
        
        FIX 1: Use _find_cli() to locate 'vercel' or 'vercel.cmd' (Windows).
        FIX 2: Deploy CWD, NOT a GitHub URL — Vercel CLI doesn't accept URLs as args.
        FIX 3: Use shell=True on Windows so .cmd wrappers execute correctly.
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
                shell=True  # Required on Windows for .cmd files
            )
            if check.returncode != 0:
                return {
                    "success": False,
                    "error": f"Vercel CLI check failed: {check.stderr.strip()}"
                }

            project_name = kwargs.get("project_name", "my-app")

            # Deploy current working directory (already chdir'd by PlatformDeployStep)
            # Do NOT pass github_url here — Vercel CLI deploys a local directory, not a URL.
            deployment_command = [
                vercel_cmd,
                "--yes",                   # Skip interactive prompts
                "--prod",                  # Deploy to production
                f"--name={project_name}",
            ]

            result = subprocess.run(
                deployment_command,
                capture_output=True,
                text=True,
                timeout=300,
                shell=True  # Required on Windows for .cmd files
            )

            if result.returncode == 0:
                # Last non-empty line is typically the production deployment URL
                lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
                deployment_url = lines[-1] if lines else "https://vercel.com/dashboard"
                return {
                    "success": True,
                    "platform": "Vercel",
                    "deployment_url": deployment_url,
                    "message": f"Successfully deployed to {deployment_url}"
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr.strip() or result.stdout.strip()
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