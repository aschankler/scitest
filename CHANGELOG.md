# Changelog

## v0.5.1 (2024-04-01)

Note: Some CLI options have changed

### Features

- Improve printing of configuration settings
- Add module-level CLI entry point

### Fixes

- Update CLI options and help text
- All config fields should be optional until tset run is started


## v0.5.0 (2024-03-20)

Note: old configs using the `%(conf_root)` syntax are no longer supported

### Features

- Configuration uses `attrs` rather than a custom interface
- Relative paths from config are resolved automatically


## v0.4.2 (2024-02-09)

### Features

- Clarify serialized file interface to consistently read both json and yaml files

### Fixes

- Remove superseded descriptor-based property interface
- Remove `strictyaml` dependency


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