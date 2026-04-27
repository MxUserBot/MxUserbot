Main directories to look at when reading the code:

- `src/mxuserbot/__main__.py` — bot launch, web-auth, crypto, handler registration.
- `src/mxuserbot/core/` — basic framework: loader, utils, security, types, callbacks.
- `src/mxuserbot/modules/core/` — built-in core modules.
- `src/mxuserbot/modules/community/` — external and user modules.
- `src/database/` — simple layer over settings storage.

If you're reading the project for the first time and want to write modules, start with:

- `docs/module-development/README.md`
