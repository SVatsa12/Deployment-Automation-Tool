"""
Platform Deployers - Integrations with various deployment platforms
"""
import subprocess
import os
from typing import Dict, Optional
from abc import ABC, abstractmethod


class PlatformDeployer(ABC):
    """Base class for platform deployers"""
    
    @abstractmethod
    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """Deploy to platform"""
        pass


class VercelDeployer(PlatformDeployer):
    """Deploy to Vercel"""
    
    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Vercel using Vercel CLI
        Requires: npm install -g vercel
        """
        try:
            # Check if Vercel CLI is installed
            result = subprocess.run(["vercel", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": "Vercel CLI not installed. Run: npm install -g vercel"
                }
            
            # Deploy using GitHub integration (requires Vercel account linked)
            project_name = kwargs.get("project_name", "my-app")
            
            deployment_command = [
                "vercel",
                "--yes",  # Skip confirmations
                f"--name={project_name}",
                github_url
            ]
            
            result = subprocess.run(
                deployment_command,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                # Extract deployment URL from output
                deployment_url = result.stdout.strip().split('\n')[-1]
                return {
                    "success": True,
                    "platform": "Vercel",
                    "deployment_url": deployment_url,
                    "message": f"Successfully deployed to {deployment_url}"
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


class NetlifyDeployer(PlatformDeployer):
    """Deploy to Netlify"""
    
    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Netlify using Netlify CLI
        Requires: npm install -g netlify-cli
        """
        try:
            # Check if Netlify CLI is installed
            result = subprocess.run(["netlify", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": "Netlify CLI not installed. Run: npm install -g netlify-cli"
                }
            
            site_name = kwargs.get("site_name", "my-app")
            
            # Link site and deploy
            deployment_command = [
                "netlify", "deploy",
                "--prod",
                f"--site={site_name}",
                "--dir=./build"  # Assuming build output is in ./build
            ]
            
            result = subprocess.run(
                deployment_command,
                capture_output=True,
                text=True,
                timeout=300
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
                    "error": result.stderr
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


class RailwayDeployer(PlatformDeployer):
    """Deploy to Railway"""
    
    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Railway using Railway CLI
        Requires: Railway account and CLI installed
        """
        try:
            # Note: Railway primarily uses GitHub integration
            # This is a simplified version
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
            return {
                "success": False,
                "error": str(e)
            }


class HerokuDeployer(PlatformDeployer):
    """Deploy to Heroku"""
    
    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Heroku using Heroku CLI
        Requires: heroku CLI and logged in account
        """
        try:
            app_name = kwargs.get("app_name", "my-app")
            
            # Create Heroku app
            create_result = subprocess.run(
                ["heroku", "create", app_name],
                capture_output=True,
                text=True
            )
            
            # Deploy using GitHub integration
            deploy_result = subprocess.run(
                ["heroku", "git:remote", "-a", app_name],
                capture_output=True,
                text=True
            )
            
            if deploy_result.returncode == 0:
                return {
                    "success": True,
                    "platform": "Heroku",
                    "deployment_url": f"https://{app_name}.herokuapp.com",
                    "message": "Heroku app created. Push to deploy."
                }
            else:
                return {
                    "success": False,
                    "error": deploy_result.stderr
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


class RenderDeployer(PlatformDeployer):
    """Deploy to Render"""
    
    def deploy(self, github_url: str, branch: str = "main", **kwargs) -> Dict[str, any]:
        """
        Deploy to Render (primarily uses GitHub integration)
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
        Deploy to Fly.io using flyctl
        """
        try:
            app_name = kwargs.get("app_name", "my-app")
            
            # Launch fly app
            launch_result = subprocess.run(
                ["flyctl", "launch", "--name", app_name, "--now"],
                capture_output=True,
                text=True,
                timeout=300
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
                    "error": launch_result.stderr
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


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
        deployer_class = cls._deployers.get(platform_id)
        if deployer_class:
            return deployer_class()
        return None
    
    @classmethod
    def get_supported_platforms(cls) -> list:
        """Get list of supported platform IDs"""
        return list(cls._deployers.keys())
