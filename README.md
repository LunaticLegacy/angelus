# Angelus

Angelus is the thin superproject for the LLMFetcher workbench deployment. The
complete implementation, its Python package, frontend, documentation and test
suite live in the [`llmfetcher`](./llmfetcher) Git submodule.

## Checkout

Clone with the submodule, or initialize it after cloning:

```bash
git clone --recurse-submodules git@github.com:LunaticLegacy/angelus.git
# or, in an existing checkout:
git submodule update --init --recursive
```

Run packaging, tests and the web workbench from the submodule directory.

## License relationship

Angelus inherits the LLMFetcher licensing model: AGPL-3.0-or-later for the
open-source distribution, with a separately negotiated commercial licensing
path described in [LICENSING.md](LICENSING.md) and
[commercial-licensing.md](commercial-licensing.md). The `llmfetcher`
submodule is a separately versioned repository and retains its own copyright
and license notices. This superproject does not alter, replace or sublicense
those terms.
