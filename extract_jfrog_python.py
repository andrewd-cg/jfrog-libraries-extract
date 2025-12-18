#!/usr/bin/env python3
"""
Extract Python packages and versions from JFrog Artifactory PyPI repository.
Queries only cached artifacts in JFrog (not upstream).
Output format matches 'pip freeze' or 'uv pip freeze'.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, Set, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


def fetch_url(url: str, auth: Tuple[str, str] = None, method: str = 'GET', data: bytes = None) -> str:
    """Fetch URL content with optional authentication."""
    try:
        req = Request(url, data=data, method=method)
        if auth:
            import base64
            credentials = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
            req.add_header('Authorization', f'Basic {credentials}')

        if data:
            req.add_header('Content-Type', 'text/plain')

        with urlopen(req, timeout=60) as response:
            return response.read().decode('utf-8')
    except HTTPError as e:
        print(f"HTTP Error {e.code} accessing {url}: {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("Authentication failed. Please check your username and password.", file=sys.stderr)
        # Try to read error response body
        try:
            error_body = e.read().decode('utf-8')
            if error_body:
                print(f"Error details: {error_body}", file=sys.stderr)
        except:
            pass
        return None
    except URLError as e:
        print(f"URL Error accessing {url}: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error accessing {url}: {e}", file=sys.stderr)
        return None


def parse_artifactory_url(url: str) -> Tuple[str, str]:
    """
    Parse JFrog URL to extract base URL and repository name.

    Example inputs:
        https://chainguard.jfrog.io/artifactory/api/pypi/python-chainguard/simple
        https://chainguard.jfrog.io/artifactory/python-chainguard

    Returns:
        (base_url, repo_name)
        e.g., ('https://chainguard.jfrog.io/artifactory', 'python-chainguard')
    """
    # Remove trailing slashes and /simple
    url = url.rstrip('/')
    if url.endswith('/simple'):
        url = url[:-7]

    # Remove /api/pypi if present
    if '/api/pypi/' in url:
        parts = url.split('/api/pypi/')
        base_url = parts[0]
        repo_name = parts[1]
    elif '/artifactory/' in url:
        parts = url.split('/artifactory/')
        base_url = parts[0] + '/artifactory'
        repo_name = parts[1]
    else:
        raise ValueError(f"Cannot parse JFrog URL: {url}. Expected format: https://host/artifactory/repo-name")

    return base_url, repo_name


def get_actual_repo_name(base_url: str, repo_name: str, auth: Tuple[str, str] = None) -> str:
    """
    Get the actual repository name by querying the storage API.
    JFrog may map virtual/remote repos to different physical names (e.g., python-chainguard -> python-chainguard-cache)
    """
    storage_url = f"{base_url}/api/storage/{repo_name}"
    result = fetch_url(storage_url, auth)

    if result:
        try:
            data = json.loads(result)
            actual_name = data.get('repo')
            if actual_name and actual_name != repo_name:
                print(f"Note: Repository name mapped from '{repo_name}' to '{actual_name}'", file=sys.stderr)
                return actual_name
        except json.JSONDecodeError:
            pass

    return repo_name


def parse_version_from_filename(filename: str) -> str:
    """Extract version from package filename."""
    # Remove file extensions
    name_without_ext = re.sub(r'\.(tar\.gz|tar\.bz2|zip|whl|egg)$', '', filename)

    # Common patterns for version extraction
    # Handle various formats: package-name-1.2.3, package_name-1.2.3, etc.
    patterns = [
        # Match versions with various suffixes (post, dev, a, b, rc)
        r'-(\d+(?:\.\d+)*(?:\.post\d+)?(?:\.dev\d+)?(?:[abc]|rc|alpha|beta)?(?:\d+)?)',
        # Match simple numeric versions
        r'-(\d+(?:\.\d+)+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, name_without_ext)
        if match:
            version = match.group(1)
            # Clean up version (remove trailing dots, hyphens)
            version = version.strip('.-')
            if version:
                return version

    return None


def extract_package_name_from_path(path: str) -> str:
    """
    Extract package name from artifact path.

    Example:
        packages/certifi/2025.7.14/certifi-2025.7.14.tar.gz -> certifi
        simple/jinja2/Jinja2-3.1.6-py3-none-any.whl -> jinja2
    """
    # Get the filename
    filename = path.split('/')[-1]

    # Remove extensions
    name = re.sub(r'\.(tar\.gz|tar\.bz2|zip|whl|egg)$', '', filename)

    # Extract package name (everything before the version pattern)
    # Match pattern: name-version
    match = re.match(r'^(.+?)-\d+', name)
    if match:
        package_name = match.group(1)
        # Normalize: replace underscores with hyphens, lowercase
        package_name = package_name.replace('_', '-').lower()
        return package_name

    return None


def get_cached_packages_aql(base_url: str, repo_name: str, auth: Tuple[str, str] = None, debug: bool = False, since_days: int = None) -> Dict[str, Set[str]]:
    """
    Use JFrog AQL to query only cached artifacts in the repository.
    Returns a dict mapping package names to sets of versions.
    If since_days is provided, only returns packages downloaded in the last X days.
    """
    aql_url = f"{base_url}/api/search/aql"

    # Build the query conditions
    if debug:
        # In debug mode, get ALL items to see what's in the repo
        aql_query = f'items.find({{"repo": "{repo_name}"}}).include("name", "path", "repo", "type", "stat.downloaded").limit(100)'
        print(f"DEBUG MODE: Showing first 100 items in repository", file=sys.stderr)
    else:
        # Build file type condition
        file_condition = '"$or": [{"name": {"$match": "*.whl"}}, {"name": {"$match": "*.tar.gz"}}, {"name": {"$match": "*.tar.bz2"}}, {"name": {"$match": "*.zip"}}, {"name": {"$match": "*.egg"}}]'

        # Add date filter if requested
        if since_days:
            from datetime import timezone
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=since_days)
            # JFrog uses ISO 8601 format: YYYY-MM-DDTHH:MM:SS.sssZ
            cutoff_str = cutoff_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            aql_query = f'items.find({{"repo": "{repo_name}", {file_condition}, "stat.downloaded": {{"$gte": "{cutoff_str}"}}}}).include("name", "path", "repo", "stat.downloaded")'
            print(f"Filtering packages downloaded since {cutoff_str} ({since_days} days ago)", file=sys.stderr)
        else:
            # AQL query to find all Python packages (wheels and source distributions)
            aql_query = f'items.find({{"repo": "{repo_name}", {file_condition}}}).include("name", "path", "repo")'

    print(f"Querying cached artifacts in {repo_name}...", file=sys.stderr)
    if debug:
        print(f"AQL Query: {aql_query}", file=sys.stderr)

    result = fetch_url(aql_url, auth, method='POST', data=aql_query.encode('utf-8'))

    if not result:
        return {}

    try:
        data = json.loads(result)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}", file=sys.stderr)
        return {}

    if 'results' not in data:
        print("No results found in AQL response", file=sys.stderr)
        return {}

    print(f"Found {len(data['results'])} cached artifacts", file=sys.stderr)

    if debug:
        print("\nDEBUG: First 20 items in repository:", file=sys.stderr)
        for item in data['results'][:20]:
            item_type = item.get('type', 'unknown')
            path = item.get('path', '')
            name = item.get('name', '')
            stats = item.get('stats', [])
            downloaded = stats[0].get('downloaded') if stats else 'N/A'
            print(f"  [{item_type}] {path}/{name} (downloaded: {downloaded})", file=sys.stderr)
        print(file=sys.stderr)

    # Parse results and group by package
    packages = {}

    for item in data['results']:
        filename = item.get('name', '')
        path = item.get('path', '')

        # Skip folders
        if item.get('type') == 'folder':
            continue

        # Extract package name
        package_name = extract_package_name_from_path(f"{path}/{filename}")
        if not package_name:
            if debug:
                print(f"DEBUG: Could not extract package name from: {path}/{filename}", file=sys.stderr)
            continue

        # Extract version
        version = parse_version_from_filename(filename)
        if not version:
            if debug:
                print(f"DEBUG: Could not extract version from: {filename}", file=sys.stderr)
            continue

        # Add to packages dict
        if package_name not in packages:
            packages[package_name] = set()
        packages[package_name].add(version)

    return packages


def get_cached_packages_storage_api(base_url: str, repo_name: str, auth: Tuple[str, str] = None) -> Dict[str, Set[str]]:
    """
    Use JFrog Storage API to browse the repository structure.
    This is a fallback method if AQL is not available.
    """
    print(f"Using Storage API to browse {repo_name}...", file=sys.stderr)

    # Try to list the repository root
    storage_url = f"{base_url}/api/storage/{repo_name}"

    result = fetch_url(storage_url, auth)
    if not result:
        return {}

    try:
        json.loads(result)  # Validate JSON but don't use it yet
    except json.JSONDecodeError:
        print("Error parsing storage API response", file=sys.stderr)
        return {}

    # This would require recursive browsing - simplified version
    print("Storage API method requires recursive browsing - using AQL is recommended", file=sys.stderr)

    return {}


def get_latest_version(versions: Set[str]) -> str:
    """Get the latest version from a set of versions."""
    if not versions:
        return None

    # Try using packaging library for proper version comparison
    try:
        from packaging.version import parse as parse_version
        return str(max(versions, key=parse_version))
    except ImportError:
        # Fallback to simple sorting
        # Sort by version parts as integers where possible
        def version_key(v):
            parts = []
            for part in re.split(r'[.\-]', v):
                try:
                    parts.append(int(part))
                except ValueError:
                    parts.append(part)
            return parts

        return sorted(versions, key=version_key)[-1]


def main():
    parser = argparse.ArgumentParser(
        description='Extract Python packages from JFrog Artifactory cache (not upstream)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --url https://chainguard.jfrog.io/artifactory/api/pypi/python-chainguard/simple
  %(prog)s --url https://chainguard.jfrog.io/artifactory/python-chainguard
  %(prog)s --url https://my.jfrog.io/artifactory/python-remote --all-versions
  %(prog)s --url https://my.jfrog.io/artifactory/python-remote --username admin --password secret

Note: This script queries ONLY cached artifacts in JFrog, not the upstream repository.
        """
    )

    parser.add_argument(
        '--url',
        required=True,
        help='JFrog Artifactory PyPI repository URL'
    )

    parser.add_argument(
        '--username',
        help='Username for authentication (optional)'
    )

    parser.add_argument(
        '--password',
        help='Password for authentication (optional)'
    )

    parser.add_argument(
        '--all-versions',
        action='store_true',
        help='Output all cached versions of each package (default: only latest version)'
    )

    parser.add_argument(
        '--package',
        help='Only output versions for a specific package'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Show all files in repository for debugging'
    )

    parser.add_argument(
        '--output',
        '-o',
        help='Output file path (e.g., requirements.txt). If not specified, outputs to stdout.'
    )

    parser.add_argument(
        '--since-days',
        type=int,
        help='Only show packages downloaded in the last X days'
    )

    args = parser.parse_args()

    auth = None
    if args.username and args.password:
        auth = (args.username, args.password)
    elif args.username or args.password:
        print("Error: Both --username and --password must be provided together", file=sys.stderr)
        sys.exit(1)

    # Parse the URL
    try:
        base_url, repo_name = parse_artifactory_url(args.url)
        print(f"JFrog Base URL: {base_url}", file=sys.stderr)
        print(f"Repository: {repo_name}", file=sys.stderr)

        # Get the actual repository name (may be different due to cache suffix)
        actual_repo_name = get_actual_repo_name(base_url, repo_name, auth)
        print(file=sys.stderr)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Get cached packages using AQL
    packages = get_cached_packages_aql(base_url, actual_repo_name, auth, debug=args.debug, since_days=args.since_days)

    if not packages:
        if args.debug:
            print("\nNo packages could be parsed from the repository", file=sys.stderr)
            print("This might mean:", file=sys.stderr)
            print("  - The repository is empty", file=sys.stderr)
            print("  - The files don't match Python package naming conventions", file=sys.stderr)
            print("  - The repository structure is different than expected", file=sys.stderr)
            sys.exit(0)
        else:
            print("No cached packages found or error accessing repository", file=sys.stderr)
            sys.exit(1)

    if not args.debug:
        print(f"Found {len(packages)} unique packages in cache", file=sys.stderr)
        print(file=sys.stderr)

    # Filter to specific package if requested
    if args.package:
        package_normalized = args.package.replace('_', '-').lower()
        if package_normalized in packages:
            packages = {package_normalized: packages[package_normalized]}
        else:
            print(f"Package '{args.package}' not found in cache", file=sys.stderr)
            sys.exit(1)

    # Generate output
    if not args.debug:
        results = []
        for package_name in sorted(packages.keys()):
            versions = packages[package_name]

            if args.all_versions:
                for version in sorted(versions):
                    results.append(f"{package_name}=={version}")
            else:
                latest = get_latest_version(versions)
                if latest:
                    results.append(f"{package_name}=={latest}")

        # Output results
        if args.output:
            # Write to file
            try:
                with open(args.output, 'w') as f:
                    for result in results:
                        f.write(result + '\n')
                print(f"Successfully wrote {len(results)} package{'s' if len(results) != 1 else ''} to {args.output}", file=sys.stderr)
            except Exception as e:
                print(f"Error writing to file {args.output}: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # Write to stdout
            print("# Cached packages and versions:", file=sys.stderr)
            print(file=sys.stderr)

            for result in results:
                print(result)

            print(file=sys.stderr)
            print(f"Total: {len(results)} package version{'s' if len(results) != 1 else ''}", file=sys.stderr)


if __name__ == '__main__':
    main()
