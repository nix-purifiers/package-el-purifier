# SPDX-License-Identifier: MIT
{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  nix,
  emacs,
  gh,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
stdenvNoCC.mkDerivation {
  pname = "package-el-purifier";
  version = "0.1.0";
  src = ../.;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/package-el-purifier" "$out/share/emacs/site-lisp"
    cp -r package_el_purifier nix lisp "$out/lib/package-el-purifier/"
    cp lisp/package-el-purifier.el "$out/share/emacs/site-lisp/"
    install -m755 bin/package-el-purifier "$out/bin/package-el-purifier"
    substituteInPlace "$out/lib/package-el-purifier/nix/realize.nix" \
      --replace-fail '@nixpkgs@' '${nixpkgsSrc}' \
      --replace-fail '@purifier@' '${purifierSrc}' \
      --replace-fail '@runtime@' "$out"
    wrapProgram "$out/bin/package-el-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python3
          nix
          emacs
          gh
        ]
      } \
      --prefix PYTHONPATH : "$out/lib/package-el-purifier" \
      --set PACKAGE_EL_PURIFIER_EMACS ${emacs}/bin/emacs \
      --set PACKAGE_EL_PURIFIER_RESOLVER "$out/lib/package-el-purifier/lisp/resolve.el" \
      --set PACKAGE_EL_PURIFIER_REALIZE "$out/lib/package-el-purifier/nix/realize.nix" \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt
    makeWrapper "$out/bin/package-el-purifier" "$out/bin/emacs" --add-flags "native --"
  '';
  meta = {
    description = "Locked, Nix-resolved Emacs packages";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "package-el-purifier";
    homepage = "https://nix-purifiers.github.io/";
  };
}
