# SPDX-License-Identifier: MIT
{ pkgs, self }:
let
  project = pkgs.package-el-purifier.buildPackageElProject {
    src = ../examples/config;
    testFile = ./integration.el;
  };
  external = pkgs.package-el-purifier.buildPackageElProject {
    src = builtins.path {
      path = ../examples/config;
      name = "emacs-with-external-lock";
      filter = path: type: baseNameOf path != "package-el-purifier.lock.json";
    };
    lockFile = ../examples/config/package-el-purifier.lock.json;
  };
  errorCheck =
    case:
    pkgs.runCommand "emacs-${case}"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.nix
        ];
        SOURCE = self;
        NIXPKGS_LIB = pkgs.path + "/lib";
        PURIFIER = self.inputs.purifier;
        PYTHONPATH = self;
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        export NIX_STATE_DIR="$TMPDIR/nix-state"
        python ${./eval-errors.py} ${case}
        touch "$out"
      '';
in
{
  unit = pkgs.runCommand "package-el-unit" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    cp -r ${self} source
    chmod -R u+w source
    cd source
    python -m unittest discover -s tests -v
    touch "$out"
  '';
  offline = project.tests;
  environment = project.packages.environment;
  release = project.release;
  external = pkgs.runCommand "emacs-external-lock" { } ''
    test ${external.packages.environment} = ${project.packages.environment}
    touch "$out"
  '';
  native-package =
    pkgs.runCommand "purifier-native-elpa-package"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.emacs
        ];
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        python ${self}/scripts/build-elpa.py "$TMPDIR/site"
        emacs --batch -Q --eval "(progn (require 'package) (setq package-user-dir \"$TMPDIR/elpa\" package-directory-list nil package-check-signature nil package-archives '((\"purifier\" . \"$TMPDIR/site/elpa/\"))) (package-refresh-contents) (package-install 'package-el-purifier) (require 'package-el-purifier))"
        touch "$out"
      '';
}
// pkgs.lib.genAttrs [ "stale" "tampered" "missing" "malformed" ] errorCheck
