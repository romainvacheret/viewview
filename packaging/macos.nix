{ pkgs, python, runtimeDependencies, src }:
let
  buildPython = python.withPackages (ps: runtimeDependencies ++ [ ps.pyinstaller ]);
in pkgs.stdenvNoCC.mkDerivation {
  pname = "Viewview-macos-arm64";
  version = "0.1.0";
  inherit src;
  nativeBuildInputs = [ buildPython pkgs.cctools ];
  dontConfigure = true;
  # PyInstaller relocates and ad-hoc signs Mach-O files. Nix fixups would
  # invalidate those signatures or reintroduce store-based library paths.
  dontFixup = true;
  buildPhase = ''
    runHook preBuild
    export PYINSTALLER_CONFIG_DIR="$TMPDIR/pyinstaller-cache"
    python -m PyInstaller --clean --noconfirm packaging/viewview.spec
    python packaging/check_macos_bundle.py dist/Viewview.app
    /usr/bin/codesign --verify --deep --strict dist/Viewview.app
    runHook postBuild
  '';
  doCheck = true;
  checkPhase = ''
    env -u PYTHONPATH -u QT_PLUGIN_PATH -u QT_QPA_PLATFORM_PLUGIN_PATH \
      QT_QPA_PLATFORM=offscreen dist/Viewview.app/Contents/MacOS/Viewview --smoke-test
  '';
  installPhase = ''
    mkdir -p "$out"
    cp -R dist/Viewview.app "$out/Viewview.app"
  '';
  meta.platforms = [ "aarch64-darwin" ];
}
