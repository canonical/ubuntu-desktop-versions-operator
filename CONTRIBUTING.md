# Contributing

To make contributions to this charm, you'll need a working
[development setup](https://documentation.ubuntu.com/juju/3.6/howto/manage-your-deployment/#set-up-your-deployment-local-testing-and-development).

You can create an environment for development with `uv`:

```shell
uv sync
```

## Testing

This project uses `uv` for managing test environments. There are some pre-configured environments
that can be used for linting and formatting code when you're preparing contributions to the charm:

```shell
uv run tox run -e format        # update your code according to linting rules
uv run tox run -e lint          # code style
uv run tox run -e static        # static type checking
uv run tox run -e unit          # unit tests
uv run tox run -e integration   # integration tests
uv run tox                      # runs 'format', 'lint', 'static', and 'unit' environments
```

## Build the charm

Build the charm in this git repository using:

```shell
charmcraft pack
```

<!-- You may want to include any contribution/style guidelines in this document>
