#!/usr/bin/env python3
"""
Extract npm packages and versions from JFrog Artifactory npm repository.
Queries only cached artifacts in JFrog (not upstream).
Output format: package@version
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, Set, Tuple, Union
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


def parse_npm_metadata(path: str, filename: str) -> Tuple[str, str]:
    """
    Extract package name and version from npm files in JFrog.

    JFrog stores npm packages in two formats:
    1. Metadata: .npm/{package}/ with package.json and {package}-{version}.json
    2. Tarballs: {hash}/{hash}/{package}/-/{package}-{version}.tgz (content-addressable storage)

    Examples:
        path: .npm/express/, filename: express-4.18.2.json -> (express, 4.18.2)
        path: .npm/@types/node/, filename: @types-node-18.11.9.json -> (@types/node, 18.11.9)
        path: hash/hash/express/-/, filename: express-4.18.2.tgz -> (express, 4.18.2)
        path: hash/hash/@babel/core/-/, filename: @babel-core-7.23.0.tgz -> (@babel/core, 7.23.0)

    Returns: (package_name, version)
    """
    # Skip package.json files (they don't have version info)
    if filename == 'package.json':
        return None, None

    # Process both .json metadata and .tgz tarballs
    if filename.endswith('.json'):
        name_without_ext = filename[:-5]
    elif filename.endswith('.tgz'):
        name_without_ext = filename[:-4]
    else:
        return None, None

    # Extract package name from path
    path_parts = path.strip('/').split('/')

    if len(path_parts) < 2:
        return None, None

    # Detect storage format
    # Format 1: .npm/{package}/ or .npm/@scope/package/
    # Format 2: {hash}/{hash}/{package}/-/ or {hash}/{hash}/@scope/package/-/

    if path_parts[0] == '.npm':
        # Metadata format: .npm/{package}/ or .npm/@scope/package/
        if len(path_parts) >= 3 and path_parts[1].startswith('@'):
            # Scoped package: .npm/@scope/package/
            scope = path_parts[1]  # @scope
            package_name_from_path = path_parts[2]  # package
            package_name = f"{scope}/{package_name_from_path}"
        else:
            # Unscoped package: .npm/{package}/
            package_name = path_parts[1]
    else:
        # Content-addressable format: {hash}/{hash}/{package}/-/ OR {hash}/{hash}/-/
        # In some cases, JFrog stores tarballs as {hash}/{hash}/-/{package}-{version}.tgz
        # without the package name in the path, so we need to extract it from the filename

        # First, try to extract version from filename to get the package name
        match = re.match(r'^(.+?)-(\d+[\d\.\-\w]*)$', name_without_ext)
        if not match:
            return None, None

        package_name_from_filename = match.group(1)
        version = match.group(2)

        # Validate version looks reasonable
        if not (version and version[0].isdigit()):
            return None, None

        # Convert package name from filename format to proper npm format
        # Filenames use: @scope-package -> @scope/package
        if package_name_from_filename.startswith('@'):
            # Scoped package: @scope-package -> @scope/package
            # Find the first hyphen after @
            parts = package_name_from_filename.split('-', 1)
            if len(parts) == 2:
                scope = parts[0]  # @scope
                package_name_part = parts[1]  # package
                package_name = f"{scope}/{package_name_part}"
            else:
                # Malformed scoped package
                return None, None
        else:
            # Unscoped package
            package_name = package_name_from_filename

        return package_name, version

    # For .npm metadata paths, extract version from filename
    # Try to match: {anything}-{version} where version starts with digit
    match = re.match(r'^(.+?)-(\d+[\d\.\-\w]*)$', name_without_ext)
    if match:
        version = match.group(2)
        # Validate version looks reasonable
        if version and version[0].isdigit():
            return package_name, version

    return None, None


def get_cached_npm_packages(base_url: str, repo_name: str, auth: Tuple[str, str] = None, debug: bool = False, since_days: int = None, include_stats: bool = False) -> Union[Dict[str, Set[str]], Dict[str, Dict[str, Tuple[str, int]]]]:
    """
    Use JFrog AQL to query only cached npm artifacts in the repository.
    Returns a dict mapping package names to sets of versions (or version stats dict).
    If since_days is provided, only returns packages downloaded in the last X days.
    If include_stats is True, returns dict mapping package names to dict of {version: (last_downloaded, download_count)}.
    Deduplicates entries with the same package+version, keeping the one with most downloads.
    """
    aql_url = f"{base_url}/api/search/aql"

    # Build the query conditions
    if debug:
        # In debug mode, get ALL items to see what's in the repo
        aql_query = f'items.find({{"repo": "{repo_name}"}}).include("name", "path", "repo", "type", "stat.downloaded", "stat.downloads").limit(100)'
        print(f"DEBUG MODE: Showing first 100 items in repository", file=sys.stderr)
    else:
        # Build file type condition for npm files (.json metadata and .tgz tarballs)
        # JFrog stores npm packages in both formats
        file_condition = '"$or": [{"name": {"$match": "*.json"}}, {"name": {"$match": "*.tgz"}}]'

        # Determine what stats to include
        if include_stats or since_days:
            stats_include = ', "stat.downloaded", "stat.downloads"'
        else:
            stats_include = ''

        # Add date filter if requested
        if since_days:
            from datetime import timezone
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=since_days)
            # JFrog uses ISO 8601 format: YYYY-MM-DDTHH:MM:SS.sssZ
            cutoff_str = cutoff_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            aql_query = f'items.find({{"repo": "{repo_name}", {file_condition}, "stat.downloaded": {{"$gte": "{cutoff_str}"}}}}).include("name", "path", "repo"{stats_include})'
            print(f"Filtering packages downloaded since {cutoff_str} ({since_days} days ago)", file=sys.stderr)
        else:
            # AQL query to find all npm files (.json metadata and .tgz tarballs)
            aql_query = f'items.find({{"repo": "{repo_name}", {file_condition}}}).include("name", "path", "repo"{stats_include})'

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

    # Parse results and group by package name
    packages = {}

    for item in data['results']:
        filename = item.get('name', '')
        path = item.get('path', '')

        # Skip folders
        if item.get('type') == 'folder':
            continue

        # Extract package name and version from path and filename
        package_name, version = parse_npm_metadata(path, filename)

        if not package_name or not version:
            if debug:
                print(f"DEBUG: Could not parse npm package from: {path}/{filename}", file=sys.stderr)
            continue

        # Extract stats if requested
        if include_stats:
            stats = item.get('stats', [])
            last_downloaded = stats[0].get('downloaded', 'Never') if stats else 'Never'
            download_count = stats[0].get('downloads', 0) if stats else 0

            # Add to packages dict with stats
            # Use a dict to deduplicate: {(package, version): (last_downloaded, download_count)}
            # Keep the entry with the highest download count
            if package_name not in packages:
                packages[package_name] = {}

            # Deduplicate: if version exists, keep the one with more downloads
            if version in packages[package_name]:
                existing_dl, existing_count = packages[package_name][version]
                # Keep the entry with higher download count, or if equal, the one with a real download date
                if download_count > existing_count or (download_count == existing_count and last_downloaded != 'Never' and existing_dl == 'Never'):
                    packages[package_name][version] = (last_downloaded, download_count)
            else:
                packages[package_name][version] = (last_downloaded, download_count)
        else:
            # Add to packages dict without stats
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

    parser.add_argument(
        '--since-days',
        type=int,
        help='Only show packages downloaded in the last X days'
    )

    parser.add_argument(
        '--csv-output',
        help='Output CSV file with download statistics (package, version, package_version, last_downloaded, download_count)'
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
    # Include stats if CSV output is requested
    include_stats = bool(args.csv_output)
    # Only apply since_days filter in AQL if NOT using CSV output (CSV gets all packages)
    aql_since_days = None if args.csv_output else args.since_days
    packages = get_cached_npm_packages(base_url, actual_repo_name, auth, debug=args.debug, since_days=aql_since_days, include_stats=include_stats)

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

    # Handle CSV output (with statistics)
    if args.csv_output and not args.debug:
        try:
            with open(args.csv_output, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['package', 'version', 'package_version', 'last_downloaded', 'download_count'])

                csv_rows = []
                for package_name in sorted(packages.keys()):
                    version_stats = packages[package_name]  # Dict of {version: (last_downloaded, download_count)}
                    for version, (last_downloaded, download_count) in version_stats.items():
                        package_version = f"{package_name}@{version}"
                        csv_rows.append([package_name, version, package_version, last_downloaded, download_count])

                # Sort by package, then version
                csv_rows.sort(key=lambda x: (x[0], x[1]))
                writer.writerows(csv_rows)

            print(f"Successfully wrote {len(csv_rows)} package-version entries to {args.csv_output}", file=sys.stderr)
        except Exception as e:
            print(f"Error writing CSV file {args.csv_output}: {e}", file=sys.stderr)
            sys.exit(1)

    # Generate output
    if not args.debug and (args.output or not args.csv_output):
        results = []

        # If since_days is used with CSV output, we need to filter here
        cutoff_date_str = None
        if args.since_days and args.csv_output:
            from datetime import timezone
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=args.since_days)
            cutoff_date_str = cutoff_date.isoformat()

        for package_name in sorted(packages.keys()):
            version_data = packages[package_name]

            # Handle both data structures: set of strings or dict of version stats
            if include_stats:
                # Extract versions from dict {version: (last_downloaded, download_count)}
                # Apply date filter if needed
                if cutoff_date_str:
                    # Filter by date for text output
                    versions = set(
                        v for v, (dl, dc) in version_data.items()
                        if dl != 'Never' and dl >= cutoff_date_str
                    )
                else:
                    versions = set(version_data.keys())
            else:
                versions = version_data

            # Skip if no versions match the filter
            if not versions:
                continue

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
            # Write to stdout (only if no CSV output)
            if not args.csv_output:
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
