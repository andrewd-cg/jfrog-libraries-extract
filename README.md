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

### Options

- `--url` - JFrog Artifactory PyPI repository URL (required)
- `--username` - Authentication username
- `--password` - Authentication password
- `--all-versions` - Show all cached versions (default: latest only)
- `--output`, `-o` - Write to file instead of stdout
- `--package` - Query specific package only
- `--debug` - Show repository contents for troubleshooting

### Examples

Show latest version of each package:
```bash
python3 extract_jfrog_python.py --url <URL> --username <USER> --password <PASS>
```

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

### Options

- `--url` - JFrog Artifactory Maven repository URL (required)
- `--username` - Authentication username
- `--password` - Authentication password
- `--all-versions` - Show all cached versions (default: latest only)
- `--output`, `-o` - Write to file instead of stdout
- `--package` - Query specific artifactId only
- `--format` - Output format: `simple`, `maven`, or `gradle` (default: simple)
- `--debug` - Show repository contents for troubleshooting

### Examples

Show latest version of each package:
```bash
python3 extract_jfrog_maven.py --url <URL> --username <USER> --password <PASS>
```

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

### Options

- `--url` - JFrog Artifactory npm repository URL (required)
- `--username` - Authentication username
- `--password` - Authentication password
- `--all-versions` - Show all cached versions (default: latest only)
- `--output`, `-o` - Write to file instead of stdout
- `--package` - Query specific package only
- `--format` - Output format: `simple`, `npm`, or `package-json` (default: simple)
- `--debug` - Show repository contents for troubleshooting

### Examples

Show latest version of each package:
```bash
python3 extract_jfrog_npm.py --url <URL> --username <USER> --password <PASS>
```

Check all cached Express versions:
```bash
python3 extract_jfrog_npm.py --url <URL> -u <USER> -p <PASS> --package express --all-versions
```

Generate package.json dependencies:
```bash
python3 extract_jfrog_npm.py --url <URL> -u <USER> -p <PASS> --format package-json -o package.json
```

---

## How It Works

All scripts use JFrog's **AQL (Artifactory Query Language)** API to query only the physical artifacts stored in your repository cache, ensuring you see exactly what's cached locally without querying upstream repositories.
