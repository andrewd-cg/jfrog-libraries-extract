# JFrog Python Package Cache Extractor

Extract Python packages and versions from JFrog Artifactory remote repository caches. Queries only what's physically cached in JFrog, not upstream.

## Usage

Extract all cached versions to a file:

```bash
python3 extract_jfrog_packages.py \
  --url https://your-domain.jfrog.io/artifactory/api/pypi/python-repo/simple \
  --username your.email@example.com \
  --password your-password \
  --all-versions \
  --output packages.txt
```

Output format (compatible with `pip install -r`):
```
aiohttp==3.9.1
flask==3.1.1
flask==3.1.2
jinja2==3.1.6
```

## Options

- `--url` - JFrog Artifactory PyPI repository URL (required)
- `--username` - Authentication username
- `--password` - Authentication password
- `--all-versions` - Show all cached versions (default: latest only)
- `--output`, `-o` - Write to file instead of stdout
- `--package` - Query specific package only
- `--debug` - Show repository contents for troubleshooting

## Examples

Show latest version of each package:
```bash
python3 extract_jfrog_packages.py --url <URL> --username <USER> --password <PASS>
```

Check all cached Flask versions:
```bash
python3 extract_jfrog_packages.py --url <URL> -u <USER> -p <PASS> --package flask --all-versions
```

Troubleshoot:
```bash
python3 extract_jfrog_packages.py --url <URL> -u <USER> -p <PASS> --debug
```

## How It Works

Uses JFrog's AQL (Artifactory Query Language) API to query only the physical artifacts stored in your repository cache. Searches for `.whl`, `.tar.gz`, and other Python package files, extracts names and versions from filenames, and outputs in `package==version` format.
