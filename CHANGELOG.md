# Changelog

## v0.4.1 (2023-08-25)

### Features

- Project metadata, readme, and build system

## v0.4.0 (2023-08-21)

Note: files for test configuration and serialized results are incompatible
with previous versions.

### Features

- Serialize to python base types rather than using strictyaml
- Validate schema with schema rather than strictyaml
- Update save file formats
- Query and quantity types use `attrs` to build classes

### Fixes

- Float printing no longer left-pads with zeros