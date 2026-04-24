import pytest
from extract_jfrog_npm import parse_npm_metadata


# --- Tarball paths ending with -/ ---

def test_3part_scoped_storybook():
    assert parse_npm_metadata('@storybook/addon-actions/-', 'addon-actions-9.0.8.tgz') == ('@storybook/addon-actions', '9.0.8')

def test_3part_scoped_aws():
    assert parse_npm_metadata('@aws-sdk/client-s3/-', 'client-s3-3.1021.0.tgz') == ('@aws-sdk/client-s3', '3.1021.0')

def test_3part_scoped_types():
    assert parse_npm_metadata('@types/node/-', 'node-25.5.0.tgz') == ('@types/node', '25.5.0')

def test_3part_scoped_babel():
    assert parse_npm_metadata('@babel/core/-', 'core-7.29.0.tgz') == ('@babel/core', '7.29.0')

def test_4part_scoped():
    assert parse_npm_metadata('node-cache/@types/node/-', 'node-18.11.9.tgz') == ('@types/node', '18.11.9')

def test_5part_scoped():
    assert parse_npm_metadata('abc123/def456/@babel/core/-', 'core-7.23.0.tgz') == ('@babel/core', '7.23.0')

def test_unscoped_3part():
    assert parse_npm_metadata('hash1/express/-', 'express-4.18.2.tgz') == ('express', '4.18.2')

def test_unscoped_4part():
    assert parse_npm_metadata('hash1/hash2/express/-', 'express-4.18.2.tgz') == ('express', '4.18.2')


# --- .npm/ metadata paths ---

def test_npm_metadata_unscoped():
    assert parse_npm_metadata('.npm/express/', 'express-4.18.2.json') == ('express', '4.18.2')

def test_npm_metadata_scoped_storybook():
    assert parse_npm_metadata('.npm/@storybook/addon-actions/@storybook', 'addon-actions-9.0.8.json') == ('@storybook/addon-actions', '9.0.8')

def test_npm_metadata_scoped_types():
    assert parse_npm_metadata('.npm/@types/node/', '@types-node-18.11.9.json') == ('@types/node', '18.11.9')


# --- Digit-suffixed package names (regression: lazy regex mis-split) ---

def test_digit_suffix_scoped_5part_tgz():
    # apidom-ns-json-schema-draft-6: regex would wrongly produce version "6-1.0.0-beta.36"
    assert parse_npm_metadata('abc123/def456/@swagger-api/apidom-ns-json-schema-draft-6/-', 'apidom-ns-json-schema-draft-6-1.0.0-beta.36.tgz') == ('@swagger-api/apidom-ns-json-schema-draft-6', '1.0.0-beta.36')

def test_digit_suffix_scoped_3part_tgz():
    assert parse_npm_metadata('@swagger-api/apidom-ns-json-schema-draft-6/-', 'apidom-ns-json-schema-draft-6-1.0.0-beta.36.tgz') == ('@swagger-api/apidom-ns-json-schema-draft-6', '1.0.0-beta.36')

def test_digit_suffix_scoped_npm_metadata():
    assert parse_npm_metadata('.npm/@swagger-api/apidom-ns-json-schema-draft-6/', 'apidom-ns-json-schema-draft-6-1.0.0-beta.36.json') == ('@swagger-api/apidom-ns-json-schema-draft-6', '1.0.0-beta.36')

def test_digit_suffix_openapi_3_0():
    # apidom-ns-openapi-3-0: regex would wrongly produce "3-0-1.0.0-beta.48"
    assert parse_npm_metadata('@swagger-api/apidom-ns-openapi-3-0/-', 'apidom-ns-openapi-3-0-1.0.0-beta.48.tgz') == ('@swagger-api/apidom-ns-openapi-3-0', '1.0.0-beta.48')

def test_digit_suffix_unscoped():
    assert parse_npm_metadata('hash1/hash2/express2/-', 'express2-4.18.2.tgz') == ('express2', '4.18.2')


# --- Skip/reject cases ---

def test_package_json_skipped():
    assert parse_npm_metadata('.npm/express/', 'package.json') == (None, None)

def test_unknown_extension():
    assert parse_npm_metadata('.npm/express/', 'express-4.18.2.txt') == (None, None)

def test_too_few_path_parts():
    assert parse_npm_metadata('solo', 'express-4.18.2.tgz') == (None, None)
