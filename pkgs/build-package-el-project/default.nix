# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  writeText,
  fetchurl,
  emacs,
  gnutar,
  gzip,
  purifier,
}:
{
  src,
  lockFile ? src + "/package-el-purifier.lock.json",
  configFile ? src + "/packages.el",
  fetchers ? { },
  testFile ? null,
  srcFilter ?
    path: type:
    !(builtins.elem (baseNameOf path) [
      ".git"
      ".package-el-purifier"
      "result"
    ]),
}:
let
  source = lib.cleanSourceWith {
    inherit src;
    filter = srcFilter;
  };
  lock = purifier.checkLock (
    (import ../../lib-overlays/default/read-lock.nix { inherit lib; }) { inherit src lockFile configFile; }
  );
  environment =
    (import ./environment.nix {
      inherit
        lib
        runCommand
        writeText
        fetchurl
        emacs
        purifier
        ;
    })
      { inherit lock fetchers; };
  tests = runCommand "package-el-project-tests" { nativeBuildInputs = [ emacs ]; } ''
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    emacs --batch -Q --load ${environment}/site-lisp/site-start.el \
      ${
        if testFile != null then
          "--load ${lib.escapeShellArg "${testFile}"} --funcall ert-run-tests-batch-and-exit"
        else
          "--eval " + lib.escapeShellArg "(mapc #'require '(${lib.concatStringsSep " " lock.selected}))"
      }
    touch "$out"
  '';
  release =
    runCommand "emacs-config-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        test -e ${tests}
        mkdir -p "$out" "$TMPDIR/release"
        cp -r ${source}/. "$TMPDIR/release/"
        chmod -R u+w "$TMPDIR/release"
        cp ${configFile} "$TMPDIR/release/packages.el"
        cp ${lockFile} "$TMPDIR/release/package-el-purifier.lock.json"
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
          -C "$TMPDIR/release" -cf - . | gzip -n > "$out/config.tar.gz"
      '';
in
builtins.seq lock {
  packages.environment = environment;
  inherit tests release;
  fetches = lock.entries;
}
