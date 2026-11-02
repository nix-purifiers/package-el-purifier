# SPDX-License-Identifier: MIT
{
  project,
  configFile,
  lockFile,
  target,
}:
let
  pkgs = import (builtins.toPath "@nixpkgs@") { };
  purifier = import (builtins.toPath "@purifier@/nix/lib") { inherit (pkgs) lib; };
  args = {
    src = /. + project;
    configFile = /. + configFile;
    lockFile = /. + lockFile;
  };
in
if target == "environment" then
  (pkgs.callPackage ./build-project.nix { inherit purifier; } args).packages.environment
else if target == "runtime" then
  pkgs.runCommand "package-el-runtime" { } ''ln -s @runtime@ "$out"''
else if target == "release" then
  (pkgs.callPackage ./build-project.nix { inherit purifier; } args).release
else
  throw "package-el-purifier: unknown realization target ${target}"
