# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  writeText,
  fetchurl,
  emacs,
  purifier,
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  versionList = xs: "(${lib.concatMapStringsSep " " toString xs})";
  packageRecord =
    p:
    "(${p.name} . [${versionList p.versionList} (${
      lib.concatMapStringsSep " " (
        r: "(${builtins.head r} ${versionList (builtins.elemAt r 1)})"
      ) p.requirements
    }) ${builtins.toJSON p.summary} ${p.kind}])";
  archive = purifier.tree (
    {
      name = "purified-elpa-archive";
      entries = checked.entries ++ [
        {
          path = "archive-contents";
          contents = "(1 ${lib.concatMapStringsSep "\n" packageRecord checked.packageMetadata})\n";
        }
      ];
      inherit runCommand fetchurl;
    }
    // fetchers
  );
  installScript = writeText "install-elpa.el" ''
    (require 'package)
    (require 'bytecomp)
    (setq package-user-dir (concat (getenv "out") "/elpa")
          package-directory-list nil
          package-check-signature nil
          package-native-compile nil
          package-quickstart t
          package-quickstart-file (concat (getenv "out") "/package-quickstart.el")
          package-archives '(("purified" . "${archive}/")))
    (package-refresh-contents)
    ${lib.concatMapStringsSep "\n" (
      p: "(unless (package-installed-p '${p.name}) (package-install '${p.name}))"
    ) checked.packageMetadata}
    (package-quickstart-refresh)
    (byte-compile-file package-quickstart-file)
  '';
  metadata = writeText "package-el-environment.json" (
    builtins.toJSON {
      archive = "${archive}/";
      inherit (checked) emacsVersion;
      packages = map (p: p.name) checked.packageMetadata;
    }
  );
in
assert
  checked.emacsVersion == emacs.version
  || throw "package-el-purifier: lock needs Emacs ${checked.emacsVersion}, but this package set has ${emacs.version}; override the scope's emacs or run package-el-purifier update with the intended toolchain";
runCommand "purified-emacs-environment" { nativeBuildInputs = [ emacs ]; } ''
  export HOME="$TMPDIR/home"
  mkdir -p "$HOME" "$out/elpa" "$out/site-lisp"
  emacs --batch -Q --load ${installScript}
  cp ${metadata} "$out/metadata.json"
  cat > "$out/site-lisp/site-start.el" <<EOF
  ;;; site-start.el --- Locked packages -*- lexical-binding: t; -*-
  (load "${../../lisp/package-el-purifier.el}" nil t)
  (setq package-el-purifier--nix-delivered t)
  (package-el-purifier--activate-environment "$out")
  EOF
''
