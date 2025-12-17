#!/usr/bin/env python3
"""
Extract npm packages and versions from JFrog Artifactory npm repository.
Queries only cached artifacts in JFrog (not upstream).
Output format: package@version
"""

import argparse
import json
import re
import sys
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
        https://chainguard.jfrog.io/artifactory/javascript-chainguard/
        https://chainguard.jfrog.io/artifactory/api/npm/javascript-chainguard

    Returns:
        (base_url, repo_name)
    """
    url = url.rstrip('/')

    # Remove /api/npm if present
    if '/api/npm/' in url:
        parts = url.split('/api/npm/')
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
    JFrog may map virtual/remote repos to different physical names
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


def parse_npm_filename(filename: str) -> Tuple[str, str]:
    """
    Extract package name and version from npm tarball filename.

    npm tarballs: package-version.tgz or @scope-package-version.tgz
    Examples:
        express-4.18.2.tgz -> (express, 4.18.2)
        @types-node-18.11.9.tgz -> (@types/node, 18.11.9)
        lodash-4.17.21.tgz -> (lodash, 4.17.21)

    Returns: (package_name, version)
    """
    if not filename.endswith('.tgz'):
        return None, None

    # Remove .tgz extension
    name_without_ext = filename[:-4]

    # Handle scoped packages: @scope-package-version.tgz
    if name_without_ext.startswith('@'):
        # Pattern: @scope-package-version
        # Need to find where the version starts (last occurrence of -\d)
        match = re.match(r'^(@[^-]+)-(.+)-(\d+.*)$', name_without_ext)
        if match:
            scope = match.group(1)
            package = match.group(2)
            version = match.group(3)
            # Reconstruct scoped package name: @scope/package
            package_name = f"{scope}/{package}"
            return package_name, version

    # Handle unscoped packages: package-version.tgz
    # Find the last dash followed by a digit (start of version)
    match = re.match(r'^(.+?)-(\d+.*)$', name_without_ext)
    if match:
        package_name = match.group(1)
        version = match.group(2)
        return package_name, version

    return None, None


def get_cached_npm_packages(base_url: str, repo_name: str, auth: Tuple[str, str] = None, debug: bool = False) -> Dict[str, Set[str]]:
    """
    Use JFrog AQL to query only cached npm artifacts in the repository.
    Returns a dict mapping package names to sets of versions.
    """
    aql_url = f"{base_url}/api/search/aql"

    if debug:
        # In debug mode, get ALL items to see what's in the repo
        aql_query = f'items.find({{"repo": "{repo_name}"}}).include("name", "path", "repo", "type").limit(100)'
        print(f"DEBUG MODE: Showing first 100 items in repository", file=sys.stderr)
    else:
        # AQL query to find all npm tarballs (.tgz files)
        aql_query = f'items.find({{"repo": "{repo_name}", "name": {{"$match": "*.tgz"}}}}).include("name", "path", "repo")'

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
            print(f"  [{item_type}] {path}/{name}", file=sys.stderr)
        print(file=sys.stderr)

    # Parse results and group by package name
    packages = {}

    for item in data['results']:
        filename = item.get('name', '')
        path = item.get('path', '')

        # Skip folders
        if item.get('type') == 'folder':
            continue

        # Extract package name and version
        package_name, version = parse_npm_filename(filename)

        if not package_name or not version:
            if debug:
                print(f"DEBUG: Could not parse npm package from: {path}/{filename}", file=sys.stderr)
            continue

        # Add to packages dict
        if package_name not in packages:
            packages[package_name] = set()
        packages[package_name].add(version)

    return packages


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
        description='Extract npm packages from JFrog Artifactory cache (not upstream)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --url https://chainguard.jfrog.io/artifactory/javascript-chainguard
  %(prog)s --url https://my.jfrog.io/artifactory/npm-remote --all-versions
  %(prog)s --url https://my.jfrog.io/artifactory/npm-remote --username admin --password secret

Note: This script queries ONLY cached artifacts in JFrog, not the upstream repository.
        """
    )

    parser.add_argument(
        '--url',
        required=True,
        help='JFrog Artifactory npm repository URL'
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
        help='Output file path. If not specified, outputs to stdout.'
    )

    parser.add_argument(
        '--format',
        choices=['npm', 'package-json', 'simple'],
        default='simple',
        help='Output format: simple (package@version), npm (npm install commands), package-json (package.json format)'
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
    packages = get_cached_npm_packages(base_url, actual_repo_name, auth, debug=args.debug)

    if not packages:
        if args.debug:
            print("\nNo packages could be parsed from the repository", file=sys.stderr)
            print("This might mean:", file=sys.stderr)
            print("  - The repository is empty", file=sys.stderr)
            print("  - The files don't match npm tarball naming conventions", file=sys.stderr)
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
        # Normalize package name for comparison
        search_package = args.package.replace('_', '-').lower()
        filtered = {k: v for k, v in packages.items() if k.lower() == search_package}
        if not filtered:
            print(f"Package '{args.package}' not found in cache", file=sys.stderr)
            sys.exit(1)
        packages = filtered

    # Generate output
    if not args.debug:
        results = []

        for package_name in sorted(packages.keys()):
            versions = packages[package_name]

            if args.all_versions:
                for version in sorted(versions):
                    if args.format == 'npm':
                        results.append(f"npm install {package_name}@{version}")
                    elif args.format == 'package-json':
                        results.append(f'  "{package_name}": "{version}"')
                    else:  # simple
                        results.append(f"{package_name}@{version}")
            else:
                # Get latest version
                latest = get_latest_version(versions)
                if latest:
                    if args.format == 'npm':
                        results.append(f"npm install {package_name}@{latest}")
                    elif args.format == 'package-json':
                        results.append(f'  "{package_name}": "{latest}"')
                    else:  # simple
                        results.append(f"{package_name}@{latest}")

        # Output results
        if args.output:
            # Write to file
            try:
                with open(args.output, 'w') as f:
                    if args.format == 'package-json':
                        f.write('{\n')
                        f.write('  "dependencies": {\n')
                    for i, result in enumerate(results):
                        if args.format == 'package-json':
                            if i < len(results) - 1:
                                f.write(result + ',\n')
                            else:
                                f.write(result + '\n')
                        else:
                            f.write(result + '\n')
                    if args.format == 'package-json':
                        f.write('  }\n')
                        f.write('}\n')
                print(f"Successfully wrote {len(results)} package{'s' if len(results) != 1 else ''} to {args.output}", file=sys.stderr)
            except Exception as e:
                print(f"Error writing to file {args.output}: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # Write to stdout
            print("# Cached npm packages and versions:", file=sys.stderr)
            print(file=sys.stderr)

            if args.format == 'package-json':
                print('{')
                print('  "dependencies": {')
            for i, result in enumerate(results):
                if args.format == 'package-json':
                    if i < len(results) - 1:
                        print(result + ',')
                    else:
                        print(result)
                else:
                    print(result)
            if args.format == 'package-json':
                print('  }')
                print('}')

            print(file=sys.stderr)
            print(f"Total: {len(results)} package version{'s' if len(results) != 1 else ''}", file=sys.stderr)


if __name__ == '__main__':
    main()
