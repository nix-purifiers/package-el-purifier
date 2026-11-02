# package-el-purifier

Locked, Nix-resolved dependencies for Emacs package.el.

## Quickstart

In your Emacs configuration directory, put the package declarations in
`packages.el`, which your `init.el` can load:

```elisp
(require 'package)
(setq package-archives
      '(("gnu" . "https://elpa.gnu.org/packages/")))
(setq package-selected-packages '(vertico))
```

Open a shell containing the CLI and Emacs wrapper:

```sh
nix shell 'github:nix-purifiers/package-el-purifier'
package-el-purifier lock
package-el-purifier prefetch
emacs
```

Commit `packages.el` and `package-el-purifier.lock.json`. The wrapper finds
these in the current directory, an explicit `--init-directory`, or your
usual `~/.emacs.d` / XDG Emacs configuration directory. It activates the
Nix-built ELPA environment before `init.el`. Existing `require` and
`use-package` declarations can load those packages normally.

The wrapper is available for installation through your normal Nix
configuration if you want it permanently. Without a lockfile, it warns and
runs ordinary Emacs with the original arguments and exit status. A stale
or invalid lock fails with a repair command.

### Use the native Emacs integration

You can keep your own Emacs and install the integration from this
repository's [ELPA archive](https://nix-purifiers.github.io/package-el-purifier/elpa/archive-contents):

```elisp
(require 'package)
(add-to-list
 'package-archives
 '("purifier" .
   "https://nix-purifiers.github.io/package-el-purifier/elpa/"))
(package-refresh-contents)
(package-install 'package-el-purifier)
```

Load it from `early-init.el`, before the rest of your configuration:

```elisp
(add-to-list 'load-path
             (expand-file-name
              "elpa/package-el-purifier-0.1.0"
              user-emacs-directory))
(require 'package-el-purifier)
(package-el-purifier-mode 1)
```

This native installation warns that the plugin is resolved impurely and
points to the Nix Emacs wrapper for pure plugin resolution. The integration
uses the CLI on `PATH`, or `nix run` when it is absent. Emacs must match the
version recorded by the lock; the wrapper supplies that toolchain.

## Development loop

After changing the declarations:

```sh
nix shell 'github:nix-purifiers/package-el-purifier'
package-el-purifier lock
package-el-purifier prefetch
emacs
```

`lock` keeps existing pins, resolving newly required packages with the
native package.el solver. Repeating it without changes leaves the lock
byte-for-byte identical. Update all packages or name the ones to update:

```sh
package-el-purifier update
package-el-purifier update vertico
package-el-purifier prefetch
```

Named updates retain other pins. If a new version needs an incompatible
locked dependency, include that dependency in the update. `packages.el`
contains package selection and archive configuration; avoid loading your
full interactive `init.el` from it.

The integration limits `package-refresh-contents` to the locked local
archive even if your configuration changes `package-archives`. Installing
an unlisted package fails and asks you to update the declarations and lock.

## Working offline

Run `prefetch` while connected. It builds the installed ELPA environment
and retains GC roots for packages and the CLI/toolchain beside the lock:

```sh
nix shell 'github:nix-purifiers/package-el-purifier'
package-el-purifier prefetch
emacs --batch -Q --eval "(require 'vertico)"
```

Native package loads and archive refreshes then use local store paths.
No project Nix files or generated development shell are needed.

## Editor

Emacs itself is the editor. The selected packages, their autoloads and the
compiled package quickstart file are installed in a per-configuration Nix
store environment. Your configuration and buffers remain in the working
tree; package byte compilation runs in the Nix sandbox.

## Troubleshooting

- **Declarations changed:** run `package-el-purifier lock`, then `prefetch`.
- **Missing or damaged lock:** `lock` regenerates it. Invalid locks never
  trigger an impure fallback.
- **Package not locked:** add it to `package-selected-packages` and relock.
- **Wrong Emacs version:** use the wrapper, or build the scope with a matching
  Emacs and regenerate the lock using that toolchain.
- **No lock warning:** check the configuration directory. Use
  `emacs --init-directory PATH` to select it explicitly.
- **Read-only ELPA directory:** packages are installed by Nix. Change the
  declarations and lock instead of modifying the store environment.

External configuration and lock paths are supported without copying them
into the source tree:

```sh
package-el-purifier \
  --config ../config/packages.el \
  --lockfile ../locks/emacs.json lock
package-el-purifier \
  --config ../config/packages.el \
  --lockfile ../locks/emacs.json prefetch
```

For the Emacs wrapper, the corresponding environment variables are
`PACKAGE_EL_PURIFIER_CONFIG` and `PACKAGE_EL_PURIFIER_LOCKFILE`.

## Supported language repositories

GNU ELPA, NonGNU ELPA, and compatible versioned HTTP(S) package archives
with native `single` or `tar` packages are supported. Builtin packages and
minimum dependency versions are checked against the locked Emacs version.
Rolling MELPA URLs are rejected because historical version artifacts are
not reliably retained. Git package managers such as straight.el and
Elpaca need their own integrations. Prerelease version vectors with
negative components are not yet supported.

The lock records native package descriptors, concrete archive URLs,
archive-byte SHA-256 hashes, Emacs builtin versions and the declaration
fingerprint. Pure evaluation validates its format, content hash and full
selected/transitive dependency closure before fetching.

## Examples

[`examples/config`](examples/config) selects Vertico from GNU ELPA. The
checks install and load it with real Emacs, test local archive refreshes
and blocked unlocked installs, and reject stale, tampered, incomplete and
malformed locks independently in Nix and Python. Host conformance tests
exercise native resolution, named updates, external locks and offline
startup against a versioned local ELPA repository on x86_64 and ARM Linux.

### Optional Nix build

The overlay adds only the `package-el-purifier` scope. Its
`buildPackageElProject` builder accepts `src`, `lockFile`, `configFile`,
`fetchers`, `srcFilter` and an optional ERT `testFile`:

```nix
let
  pkgs = import nixpkgs {
    inherit system;
    overlays = [ purifier.overlays.default ];
  };
  project =
    pkgs.package-el-purifier.buildPackageElProject {
      src = ./.;
      lockFile = ../locks/emacs.json;
    };
in {
  packages.default = project.packages.environment;
  checks.default = project.tests;
}
```

The result exposes `packages.environment`, `tests`, `release` and `fetches`.
The builder uses named `callPackage` arguments and supports scope overrides
and custom fetchers. `lib.package-el-purifier.readLock` exposes the shared
lock-reader shape without import-from-derivation.

`release` contains a deterministic configuration archive with the selected
lock. To publish that Nix-built artifact to a GitHub release:

```sh
package-el-purifier publish \
  --repo OWNER/CONFIGURATION --tag v1.0.0
```

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).
