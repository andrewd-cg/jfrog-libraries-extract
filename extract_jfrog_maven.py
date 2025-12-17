#!/usr/bin/env python3
"""
Extract Maven packages and versions from JFrog Artifactory Maven repository.
Queries only cached artifacts in JFrog (not upstream).
Output format: groupId:artifactId:version
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
        https://chainguard.jfrog.io/artifactory/java-chainguard/
        https://chainguard.jfrog.io/artifactory/java-chainguard

    Returns:
        (base_url, repo_name)
    """
    url = url.rstrip('/')

    if '/artifactory/' in url:
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


def parse_maven_path(path: str, filename: str) -> Tuple[str, str, str]:
    """
    Extract groupId, artifactId, and version from Maven artifact path.

    Maven structure: groupId/artifactId/version/artifact-version.extension
    Example: org/springframework/spring-core/5.3.1/spring-core-5.3.1.jar
    Returns: (groupId, artifactId, version)
    """
    # Skip non-primary artifacts (sources, javadoc, checksums, signatures)
    if any(filename.endswith(ext) for ext in ['.md5', '.sha1', '.sha256', '.sha512', '.asc', '.pom.asc']):
        return None, None, None

    # We primarily care about .jar files and .pom files
    if not (filename.endswith('.jar') or filename.endswith('.pom')):
        return None, None, None

    # Skip sources and javadoc
    if '-sources.jar' in filename or '-javadoc.jar' in filename or '-tests.jar' in filename:
        return None, None, None

    # Parse path: groupId/artifactId/version/filename
    path_parts = path.strip('/').split('/')

    if len(path_parts) < 3:
        return None, None, None

    version = path_parts[-1]
    artifact_id = path_parts[-2]
    group_id = '.'.join(path_parts[:-2])

    # Validate that filename matches expected pattern: artifactId-version.extension
    expected_prefix = f"{artifact_id}-{version}"
    if not filename.startswith(expected_prefix):
        return None, None, None

    return group_id, artifact_id, version


def get_cached_maven_packages(base_url: str, repo_name: str, auth: Tuple[str, str] = None, debug: bool = False) -> Dict[Tuple[str, str], Set[str]]:
    """
    Use JFrog AQL to query only cached Maven artifacts in the repository.
    Returns a dict mapping (groupId, artifactId) to sets of versions.
    """
    aql_url = f"{base_url}/api/search/aql"

    if debug:
        # In debug mode, get ALL items to see what's in the repo
        aql_query = f'items.find({{"repo": "{repo_name}"}}).include("name", "path", "repo", "type").limit(100)'
        print(f"DEBUG MODE: Showing first 100 items in repository", file=sys.stderr)
    else:
        # AQL query to find all Maven artifacts (.jar and .pom files)
        aql_query = f'items.find({{"repo": "{repo_name}", "$or": [{{"name": {{"$match": "*.jar"}}}}, {{"name": {{"$match": "*.pom"}}}}]}}).include("name", "path", "repo")'

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

    # Parse results and group by (groupId, artifactId)
    packages = {}

    for item in data['results']:
        filename = item.get('name', '')
        path = item.get('path', '')

        # Skip folders
        if item.get('type') == 'folder':
            continue

        # Extract Maven coordinates
        group_id, artifact_id, version = parse_maven_path(path, filename)

        if not group_id or not artifact_id or not version:
            if debug:
                print(f"DEBUG: Could not parse Maven coordinates from: {path}/{filename}", file=sys.stderr)
            continue

        # Add to packages dict
        key = (group_id, artifact_id)
        if key not in packages:
            packages[key] = set()
        packages[key].add(version)

    return packages


def main():
    parser = argparse.ArgumentParser(
        description='Extract Maven packages from JFrog Artifactory cache (not upstream)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --url https://chainguard.jfrog.io/artifactory/java-chainguard
  %(prog)s --url https://my.jfrog.io/artifactory/maven-remote --all-versions
  %(prog)s --url https://my.jfrog.io/artifactory/maven-remote --username admin --password secret

Note: This script queries ONLY cached artifacts in JFrog, not the upstream repository.
        """
    )

    parser.add_argument(
        '--url',
        required=True,
        help='JFrog Artifactory Maven repository URL'
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
        help='Only output versions for a specific artifactId'
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
        choices=['maven', 'gradle', 'simple'],
        default='simple',
        help='Output format: simple (groupId:artifactId:version), maven (XML), gradle (Gradle syntax)'
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
    packages = get_cached_maven_packages(base_url, actual_repo_name, auth, debug=args.debug)

    if not packages:
        if args.debug:
            print("\nNo packages could be parsed from the repository", file=sys.stderr)
            print("This might mean:", file=sys.stderr)
            print("  - The repository is empty", file=sys.stderr)
            print("  - The files don't match Maven artifact naming conventions", file=sys.stderr)
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
        filtered = {k: v for k, v in packages.items() if k[1] == args.package}
        if not filtered:
            print(f"Package '{args.package}' not found in cache", file=sys.stderr)
            sys.exit(1)
        packages = filtered

    # Generate output
    if not args.debug:
        results = []

        for (group_id, artifact_id) in sorted(packages.keys()):
            versions = packages[(group_id, artifact_id)]

            if args.all_versions:
                for version in sorted(versions):
                    if args.format == 'maven':
                        results.append(f"<dependency>\n  <groupId>{group_id}</groupId>\n  <artifactId>{artifact_id}</artifactId>\n  <version>{version}</version>\n</dependency>")
                    elif args.format == 'gradle':
                        results.append(f"implementation '{group_id}:{artifact_id}:{version}'")
                    else:  # simple
                        results.append(f"{group_id}:{artifact_id}:{version}")
            else:
                # Get latest version
                latest = sorted(versions)[-1]  # Simple sort, may not handle all version schemes perfectly
                if args.format == 'maven':
                    results.append(f"<dependency>\n  <groupId>{group_id}</groupId>\n  <artifactId>{artifact_id}</artifactId>\n  <version>{latest}</version>\n</dependency>")
                elif args.format == 'gradle':
                    results.append(f"implementation '{group_id}:{artifact_id}:{latest}'")
                else:  # simple
                    results.append(f"{group_id}:{artifact_id}:{latest}")

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
            print("# Cached Maven packages and versions:", file=sys.stderr)
            print(file=sys.stderr)

            for result in results:
                print(result)

            print(file=sys.stderr)
            print(f"Total: {len(results)} package version{'s' if len(results) != 1 else ''}", file=sys.stderr)


if __name__ == '__main__':
    main()
