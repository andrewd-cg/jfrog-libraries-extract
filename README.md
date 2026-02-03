# JFrog Package Cache Extractors

Extract packages and versions from JFrog Artifactory remote repository caches. Queries only what's physically cached in JFrog, not upstream.

## Python Packages

Extract Python packages from PyPI remote repositories.

### Usage

```bash
python3 extract_jfrog_python.py \
  --url https://your-domain.jfrog.io/artifactory/api/pypi/python-repo/simple \
  --username your.email@example.com \
  --password your-password \
  --all-versions \
  --output python-packages.txt
```

**Output format** (compatible with `pip install -r`):
```
aiohttp==3.9.1
flask==3.1.1
flask==3.1.2
jinja2==3.1.6
```

**CSV output format** (with `--csv-output`):
```csv
package,version,package_version,last_downloaded,download_count
aiohttp,3.9.1,aiohttp==3.9.1,2025-12-15T10:30:45.123Z,42
flask,3.1.1,flask==3.1.1,2025-12-10T08:15:22.456Z,15
flask,3.1.2,flask==3.1.2,2025-12-17T14:22:33.789Z,28
jinja2,3.1.6,jinja2==3.1.6,2025-12-16T12:45:11.234Z,35
```

### Options

- `--url` - JFrog Artifactory PyPI repository URL (required)
- `--username` - Authentication username
- `--password` - Authentication password
- `--all-versions` - Show all cached versions (default: latest only)
- `--output`, `-o` - Write to file instead of stdout (simple text format)
- `--csv-output` - Write CSV file with download statistics (package, version, package_version, last_downloaded, download_count). **Always exports ALL packages regardless of `--since-days`**
- `--package` - Query specific package only
- `--since-days` - Filter packages downloaded in the last X days (applies to `--output` only; `--csv-output` always shows all packages)
- **Note**: `--output` and `--csv-output` can be used together - CSV gets full inventory, text output respects `--since-days` filter
- `--debug` - Show repository contents for troubleshooting

### Examples

Show latest version of each package:
```bash
python3 extract_jfrog_python.py --url <URL> --username <USER> --password <PASS>
```

Show packages downloaded in the last 30 days:
```bash
python3 extract_jfrog_python.py --url <URL> -u <USER> -p <PASS> --since-days 30 -o recent-packages.txt
```

Export all packages with download statistics to CSV:
```bash
python3 extract_jfrog_python.py --url <URL> -u <USER> -p <PASS> --csv-output all-packages-stats.csv
```

Export both formats: CSV with ALL packages, text with only recent (30 days):
```bash
python3 extract_jfrog_python.py --url <URL> -u <USER> -p <PASS> --since-days 30 --output recent-packages.txt --csv-output all-packages-stats.csv
```
*Note: `all-packages-stats.csv` contains ALL packages with stats, `recent-packages.txt` contains only packages from last 30 days*

Check all cached Flask versions:
```bash
python3 extract_jfrog_python.py --url <URL> -u <USER> -p <PASS> --package flask --all-versions
```

---

## Maven Packages

Extract Maven packages from Maven remote repositories.

### Usage

```bash
python3 extract_jfrog_maven.py \
  --url https://your-domain.jfrog.io/artifactory/java-repo \
  --username your.email@example.com \
  --password your-password \
  --all-versions \
  --output maven-packages.txt
```

**Output formats:**

Simple (default):
```
org.springframework:spring-core:5.3.1
org.springframework:spring-core:5.3.2
com.google.guava:guava:31.1-jre
```

Maven XML (`--format maven`):
```xml
<dependency>
  <groupId>org.springframework</groupId>
  <artifactId>spring-core</artifactId>
  <version>5.3.1</version>
</dependency>
```

Gradle (`--format gradle`):
```
implementation 'org.springframework:spring-core:5.3.1'
```

**CSV output format** (with `--csv-output`):
```csv
groupId,artifactId,version,package_version,last_downloaded,download_count
org.springframework,spring-core,5.3.1,org.springframework:spring-core:5.3.1,2025-12-15T10:30:45.123Z,42
org.springframework,spring-core,5.3.2,org.springframework:spring-core:5.3.2,2025-12-17T14:22:33.789Z,28
com.google.guava,guava,31.1-jre,com.google.guava:guava:31.1-jre,2025-12-16T12:45:11.234Z,35
```

### Options

- `--url` - JFrog Artifactory Maven repository URL (required)
- `--username` - Authentication username
- `--password` - Authentication password
- `--all-versions` - Show all cached versions (default: latest only)
- `--output`, `-o` - Write to file instead of stdout (simple text format)
- `--csv-output` - Write CSV file with download statistics (groupId, artifactId, version, package_version, last_downloaded, download_count). **Always exports ALL packages regardless of `--since-days`**
- `--package` - Query specific artifactId only
- `--format` - Output format: `simple`, `maven`, or `gradle` (default: simple)
- `--since-days` - Filter packages downloaded in the last X days (applies to `--output` only; `--csv-output` always shows all packages)
- **Note**: `--output` and `--csv-output` can be used together - CSV gets full inventory, text output respects `--since-days` filter
- `--debug` - Show repository contents for troubleshooting

### Examples

Show latest version of each package:
```bash
python3 extract_jfrog_maven.py --url <URL> --username <USER> --password <PASS>
```

Show packages downloaded in the last 30 days:
```bash
python3 extract_jfrog_maven.py --url <URL> -u <USER> -p <PASS> --since-days 30 -o recent-maven.txt
```

Export all packages with download statistics to CSV:
```bash
python3 extract_jfrog_maven.py --url <URL> -u <USER> -p <PASS> --csv-output all-maven-stats.csv
```

Export both formats: CSV with ALL packages, text with only recent (30 days):
```bash
python3 extract_jfrog_maven.py --url <URL> -u <USER> -p <PASS> --since-days 30 --output recent-maven.txt --csv-output all-maven-stats.csv
```
*Note: `all-maven-stats.csv` contains ALL packages with stats, `recent-maven.txt` contains only packages from last 30 days*

Check all cached Spring Core versions:
```bash
python3 extract_jfrog_maven.py --url <URL> -u <USER> -p <PASS> --package spring-core --all-versions
```

Generate Maven XML dependencies:
```bash
python3 extract_jfrog_maven.py --url <URL> -u <USER> -p <PASS> --format maven -o dependencies.xml
```

---

## npm Packages

Extract npm packages from npm remote repositories.

### Usage

```bash
python3 extract_jfrog_npm.py \
  --url https://your-domain.jfrog.io/artifactory/javascript-repo \
  --username your.email@example.com \
  --password your-password \
  --all-versions \
  --output npm-packages.txt
```

**Output formats:**

Simple (default):
```
express@4.18.2
lodash@4.17.21
@types/node@18.11.9
```

npm install commands (`--format npm`):
```
npm install express@4.18.2
npm install lodash@4.17.21
npm install @types/node@18.11.9
```

package.json format (`--format package-json`):
```json
{
  "dependencies": {
    "express": "4.18.2",
    "lodash": "4.17.21",
    "@types/node": "18.11.9"
  }
}
```

**CSV output format** (with `--csv-output`):
```csv
package,version,package_version,last_downloaded,download_count
express,4.18.2,express@4.18.2,2025-12-15T10:30:45.123Z,42
lodash,4.17.21,lodash@4.17.21,2025-12-17T14:22:33.789Z,28
@types/node,18.11.9,@types/node@18.11.9,2025-12-16T12:45:11.234Z,35
```

**Note**: JFrog stores npm packages in multiple formats (tarball + metadata). The script automatically deduplicates entries, keeping the one with the most downloads.

### Options

- `--url` - JFrog Artifactory npm repository URL (required)
- `--username` - Authentication username
- `--password` - Authentication password
- `--all-versions` - Show all cached versions (default: latest only)
- `--output`, `-o` - Write to file instead of stdout (simple text format)
- `--csv-output` - Write CSV file with download statistics (package, version, package_version, last_downloaded, download_count). **Always exports ALL packages regardless of `--since-days`**
- `--package` - Query specific package only
- `--format` - Output format: `simple`, `npm`, or `package-json` (default: simple)
- `--since-days` - Filter packages downloaded in the last X days (applies to `--output` only; `--csv-output` always shows all packages)
- **Note**: `--output` and `--csv-output` can be used together - CSV gets full inventory, text output respects `--since-days` filter
- `--debug` - Show repository contents for troubleshooting

### Examples

Show latest version of each package:
```bash
python3 extract_jfrog_npm.py --url <URL> --username <USER> --password <PASS>
```

Show packages downloaded in the last 30 days:
```bash
python3 extract_jfrog_npm.py --url <URL> -u <USER> -p <PASS> --since-days 30 -o recent-npm.txt
```

Export all packages with download statistics to CSV:
```bash
python3 extract_jfrog_npm.py --url <URL> -u <USER> -p <PASS> --csv-output all-npm-stats.csv
```

Export both formats: CSV with ALL packages, text with only recent (30 days):
```bash
python3 extract_jfrog_npm.py --url <URL> -u <USER> -p <PASS> --since-days 30 --output recent-npm.txt --csv-output all-npm-stats.csv
```
*Note: `all-npm-stats.csv` contains ALL packages with stats, `recent-npm.txt` contains only packages from last 30 days*

Check all cached Express versions:
```bash
python3 extract_jfrog_npm.py --url <URL> -u <USER> -p <PASS> --package express --all-versions
```

Check scoped package versions (e.g., @types/node):
```bash
python3 extract_jfrog_npm.py --url <URL> -u <USER> -p <PASS> --package @types/node --all-versions
```

Generate package.json dependencies:
```bash
python3 extract_jfrog_npm.py --url <URL> -u <USER> -p <PASS> --format package-json -o package.json
```

---

## How It Works

All scripts use JFrog's **AQL (Artifactory Query Language)** API to query only the physical artifacts stored in your repository cache, ensuring you see exactly what's cached locally without querying upstream repositories.
