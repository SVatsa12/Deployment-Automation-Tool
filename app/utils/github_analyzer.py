"""
GitHub Repository Analyzer
Detects project type and suggests compatible deployment platforms
"""
import requests
from typing import Dict, List, Optional


class GitHubAnalyzer:
    """Analyzes GitHub repositories to detect project type and compatible platforms"""
    
    @staticmethod
    def parse_github_url(url: str) -> Dict[str, str]:
        """Extract owner and repo from GitHub URL"""
        # https://github.com/owner/repo.git -> owner, repo
        url = url.replace('.git', '').replace('https://github.com/', '')
        parts = url.split('/')
        
        if len(parts) >= 2:
            return {
                "owner": parts[0],
                "repo": parts[1]
            }
        raise ValueError("Invalid GitHub URL format")
    
    @staticmethod
    def detect_project_type(owner: str, repo: str) -> Dict[str, any]:
        """
        Detect project type by checking repository files
        Uses GitHub API to check for key files
        """
        base_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
        
        try:
            response = requests.get(base_url, timeout=10)
            if response.status_code != 200:
                return {"error": "Cannot access repository", "files": []}
            
            files = response.json()
            file_names = [f['name'] for f in files if f['type'] == 'file']
            
            project_info = {
                "detected_type": "unknown",
                "framework": None,
                "files_found": file_names,
                "build_tool": None,
                "runtime": None
            }
            
            # Detect Node.js/JavaScript projects
            if 'package.json' in file_names:
                project_info["runtime"] = "node"
                project_info["detected_type"] = "nodejs"
                
                # Try to detect framework from package.json
                package_response = requests.get(f"{base_url}/package.json")
                if package_response.status_code == 200:
                    import base64
                    import json
                    content = base64.b64decode(package_response.json()['content']).decode('utf-8')
                    package_data = json.loads(content)
                    
                    dependencies = {**package_data.get('dependencies', {}), 
                                  **package_data.get('devDependencies', {})}
                    
                    if 'next' in dependencies:
                        project_info["framework"] = "nextjs"
                    elif 'react' in dependencies:
                        project_info["framework"] = "react"
                    elif 'vue' in dependencies:
                        project_info["framework"] = "vue"
                    elif 'angular' in dependencies:
                        project_info["framework"] = "angular"
                    elif 'express' in dependencies:
                        project_info["framework"] = "express"
                    elif 'nuxt' in dependencies:
                        project_info["framework"] = "nuxt"
            
            # Detect Python projects
            elif 'requirements.txt' in file_names or 'setup.py' in file_names or 'pyproject.toml' in file_names:
                project_info["runtime"] = "python"
                project_info["detected_type"] = "python"
                
                if 'requirements.txt' in file_names:
                    req_response = requests.get(f"{base_url}/requirements.txt")
                    if req_response.status_code == 200:
                        import base64
                        content = base64.b64decode(req_response.json()['content']).decode('utf-8')
                        
                        if 'django' in content.lower():
                            project_info["framework"] = "django"
                        elif 'flask' in content.lower():
                            project_info["framework"] = "flask"
                        elif 'fastapi' in content.lower():
                            project_info["framework"] = "fastapi"
            
            # Detect static sites
            elif 'index.html' in file_names:
                project_info["detected_type"] = "static"
                project_info["runtime"] = "static"
                
                if any(f.endswith('.jsx') or f.endswith('.tsx') for f in file_names):
                    project_info["framework"] = "react-static"
            
            # Detect Go projects
            elif 'go.mod' in file_names or 'go.sum' in file_names:
                project_info["runtime"] = "go"
                project_info["detected_type"] = "go"
            
            # Detect Java/Maven projects
            elif 'pom.xml' in file_names:
                project_info["runtime"] = "java"
                project_info["detected_type"] = "java"
                project_info["build_tool"] = "maven"
            
            # Detect Ruby projects
            elif 'Gemfile' in file_names:
                project_info["runtime"] = "ruby"
                project_info["detected_type"] = "ruby"
                
                if 'config.ru' in file_names:
                    project_info["framework"] = "rails"
            
            # Detect Rust projects
            elif 'Cargo.toml' in file_names:
                project_info["runtime"] = "rust"
                project_info["detected_type"] = "rust"
            
            # Detect PHP projects
            elif 'composer.json' in file_names:
                project_info["runtime"] = "php"
                project_info["detected_type"] = "php"
            
            # Detect Docker projects
            if 'Dockerfile' in file_names:
                project_info["has_dockerfile"] = True
            
            return project_info
            
        except Exception as e:
            return {"error": str(e), "detected_type": "unknown"}
    
    @staticmethod
    def get_compatible_platforms(project_info: Dict) -> List[Dict[str, any]]:
        """
        Return list of compatible deployment platforms based on project type
        """
        detected_type = project_info.get("detected_type", "unknown")
        framework = project_info.get("framework")
        has_dockerfile = project_info.get("has_dockerfile", False)
        
        platforms = []
        
        # Vercel - Great for frontend frameworks
        if detected_type in ["nodejs", "static"] or framework in ["nextjs", "react", "vue", "nuxt", "angular"]:
            platforms.append({
                "name": "Vercel",
                "id": "vercel",
                "description": "Best for Next.js, React, Vue, and static sites",
                "free_tier": True,
                "deployment_time": "~2 min",
                "features": ["Auto HTTPS", "CDN", "Serverless Functions"],
                "recommended": framework == "nextjs"
            })
        
        # Netlify - Great for static sites and JAMstack
        if detected_type in ["nodejs", "static"]:
            platforms.append({
                "name": "Netlify",
                "id": "netlify",
                "description": "Perfect for static sites and JAMstack apps",
                "free_tier": True,
                "deployment_time": "~2 min",
                "features": ["Forms", "Functions", "CDN", "Split Testing"],
                "recommended": detected_type == "static"
            })
        
        # Railway - Great for backends and full-stack apps
        if detected_type in ["nodejs", "python", "go", "ruby", "rust"]:
            platforms.append({
                "name": "Railway",
                "id": "railway",
                "description": "Easy deployment for any backend service",
                "free_tier": True,
                "deployment_time": "~3 min",
                "features": ["Databases", "Cron Jobs", "Private Networking"],
                "recommended": framework in ["express", "fastapi", "flask", "django"]
            })
        
        # Heroku - Supports many languages
        if detected_type in ["nodejs", "python", "ruby", "java", "php", "go"]:
            platforms.append({
                "name": "Heroku",
                "id": "heroku",
                "description": "Classic PaaS, supports many languages",
                "free_tier": False,
                "deployment_time": "~4 min",
                "features": ["Add-ons", "Dyno Management", "CI/CD"],
                "recommended": False
            })
        
        # Render - Modern alternative to Heroku
        if detected_type in ["nodejs", "python", "ruby", "go", "rust", "static"]:
            platforms.append({
                "name": "Render",
                "id": "render",
                "description": "Modern cloud platform, Heroku alternative",
                "free_tier": True,
                "deployment_time": "~3 min",
                "features": ["Auto Deploy", "Free SSL", "DDoS Protection"],
                "recommended": False
            })
        
        # Fly.io - Great for Docker and full-stack apps
        if has_dockerfile or detected_type in ["nodejs", "python", "go", "ruby"]:
            platforms.append({
                "name": "Fly.io",
                "id": "fly",
                "description": "Run apps close to users worldwide",
                "free_tier": True,
                "deployment_time": "~3 min",
                "features": ["Edge Deployment", "Global Network", "Auto Scaling"],
                "recommended": has_dockerfile
            })
        
        # Cloudflare Pages - Great for static sites
        if detected_type in ["static", "nodejs"]:
            platforms.append({
                "name": "Cloudflare Pages",
                "id": "cloudflare",
                "description": "Fast static site hosting on Cloudflare network",
                "free_tier": True,
                "deployment_time": "~2 min",
                "features": ["Unlimited Bandwidth", "CDN", "Web Analytics"],
                "recommended": False
            })
        
        # DigitalOcean App Platform
        if detected_type in ["nodejs", "python", "go", "php", "ruby", "static"]:
            platforms.append({
                "name": "DigitalOcean App Platform",
                "id": "digitalocean",
                "description": "Simple deployment on DigitalOcean",
                "free_tier": True,
                "deployment_time": "~4 min",
                "features": ["Managed Databases", "Auto Scaling", "Load Balancing"],
                "recommended": False
            })
        
        # If no specific platform detected, offer Docker-based solutions
        if not platforms or has_dockerfile:
            platforms.append({
                "name": "Docker (Generic)",
                "id": "docker",
                "description": "Deploy as Docker container to any platform",
                "free_tier": None,
                "deployment_time": "Varies",
                "features": ["Portable", "Consistent", "Works Anywhere"],
                "recommended": has_dockerfile and not platforms
            })
        
        return platforms
    
    @staticmethod
    def analyze_repository(github_url: str) -> Dict[str, any]:
        """
        Main analysis function - analyzes repo and returns compatible platforms
        """
        try:
            # Parse GitHub URL
            parsed = GitHubAnalyzer.parse_github_url(github_url)
            owner = parsed["owner"]
            repo = parsed["repo"]
            
            # Detect project type
            project_info = GitHubAnalyzer.detect_project_type(owner, repo)
            
            # Get compatible platforms
            platforms = GitHubAnalyzer.get_compatible_platforms(project_info)
            
            return {
                "repository": f"{owner}/{repo}",
                "github_url": github_url,
                "project_type": project_info.get("detected_type"),
                "framework": project_info.get("framework"),
                "runtime": project_info.get("runtime"),
                "compatible_platforms": platforms,
                "analysis_success": True
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "analysis_success": False,
                "compatible_platforms": []
            }
