# SPDX-License-Identifier: MIT
{ lib }:
{
  src,
  lockFile ? src + "/package-el-purifier.lock.json",
  configFile ? src + "/packages.el",
}:
let
  problem =
    message:
    "package-el-purifier: ${message}; run package-el-purifier lock (use --lockfile for external locks)";
  exists = builtins.pathExists lockFile && builtins.pathExists configFile;
  data =
    if exists then
      builtins.addErrorContext (problem "cannot parse lockfile") (
        builtins.fromJSON (builtins.readFile lockFile)
      )
    else
      { };
  nameOK = name: builtins.isString name && builtins.match "[A-Za-z0-9][A-Za-z0-9+-]*" name != null;
  packages = data.packages or [ ];
  selected = data.selected or [ ];
  builtinsMap = data.builtins or { };
  builtinsList = builtins.attrNames builtinsMap;
  names = map (p: p.name) packages;
  required = selected ++ lib.concatMap (p: map builtins.head p.requirements) packages;
  available = names ++ builtinsList;
  vectorOK = xs: builtins.isList xs && builtins.all (x: builtins.isInt x && x >= 0) xs;
  packageOK =
    p:
    builtins.isAttrs p
    && nameOK (p.name or null)
    && builtins.isString (p.version or null)
    && builtins.match "[0-9][A-Za-z0-9.-]*" p.version != null
    && !(lib.hasInfix ".." p.version)
    && vectorOK (p.versionList or null)
    && p.versionList != [ ]
    && builtins.elem (p.kind or null) [
      "tar"
      "single"
    ]
    && builtins.isString (p.summary or null)
    && builtins.isString (p.url or null)
    && builtins.match "https?://[^/@#]+[^#]*" p.url != null
    && builtins.isString (p.hash or null)
    && builtins.match "sha256-[A-Za-z0-9+/]{43}=" p.hash != null
    && builtins.isList (p.requirements or null)
    && builtins.all (
      r:
      builtins.isList r
      && builtins.length r == 2
      && nameOK (builtins.head r)
      && vectorOK (builtins.elemAt r 1)
    ) p.requirements;
  versions =
    builtinsMap
    // builtins.listToAttrs (
      map (p: {
        name = p.name;
        value = p.versionList;
      }) packages
    );
  versionString = xs: lib.concatMapStringsSep "." toString xs;
  versionsOK = builtins.all (
    p:
    builtins.all (
      r:
      !(builtins.hasAttr (builtins.head r) versions)
      || lib.versionAtLeast (versionString versions.${builtins.head r}) (
        versionString (builtins.elemAt r 1)
      )
    ) p.requirements
  ) packages;
  problems = map problem (
    if !exists then
      [ "missing package declarations or lockfile" ]
    else if !builtins.isAttrs data || (data.version or null) != 1 then
      [ "unsupported lock format" ]
    else if
      (data.contentHash or null)
      != builtins.hashString "sha256" (builtins.toJSON (removeAttrs data [ "contentHash" ]))
    then
      [ "contentHash mismatch" ]
    else if (data.configHash or null) != builtins.hashFile "sha256" configFile then
      [ "package declarations changed after locking" ]
    else if !builtins.isString (data.emacsVersion or null) then
      [ "missing Emacs version" ]
    else if !builtins.isList packages || !builtins.isList selected || !builtins.isAttrs builtinsMap then
      [ "invalid package lists" ]
    else if !builtins.all nameOK (selected ++ builtinsList) || !builtins.all packageOK packages then
      [ "invalid package metadata" ]
    else if builtins.length (lib.unique names) != builtins.length names then
      [ "duplicate package names" ]
    else if !builtins.all vectorOK (builtins.attrValues builtinsMap) then
      [ "invalid builtin versions" ]
    else if !versionsOK then
      [ "a locked dependency version is below its native requirement" ]
    else if builtins.any (name: !(builtins.elem name available)) required then
      [ "missing selected or transitive package entries" ]
    else
      [ ]
  );
  usable = problems == [ ];
in
{
  purifier = "package-el-purifier";
  inherit problems;
  outputs.environment = { };
  entries =
    if !usable then
      [ ]
    else
      map (p: {
        path = "${p.name}-${p.version}.${if p.kind == "single" then "el" else "tar"}";
        inherit (p) url hash;
        mirrors = [ ];
      }) packages;
  packageMetadata = if usable then packages else [ ];
  selected = if usable then selected else [ ];
  emacsVersion = data.emacsVersion or "";
}
