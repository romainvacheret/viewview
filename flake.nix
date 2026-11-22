{
  description = "Viewview development environment and portable application builds";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    nix-appimage.url = "github:ralismark/nix-appimage";
    nix-appimage.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, nix-appimage }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" ];
      perSystem = nixpkgs.lib.genAttrs systems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python3;
          runtimeDependencies = with pkgs.python3Packages; [
            pyside6 pillow pillow-heif exifread hachoir
          ];
          environment = python.withPackages (_: runtimeDependencies);
          src = pkgs.lib.fileset.toSource {
            root = ./.;
            fileset = pkgs.lib.fileset.unions [ ./viewview ./packaging ./pyproject.toml ];
          };
          application = python.pkgs.buildPythonApplication {
            pname = "viewview";
            version = "0.1.0";
            inherit src;
            pyproject = true;
            build-system = [ python.pkgs.setuptools ];
            dependencies = runtimeDependencies;
            nativeBuildInputs = [ pkgs.qt6.wrapQtAppsHook ];
            buildInputs = [ pkgs.qt6.qtbase ];
            dontWrapQtApps = true;
            preFixup = ''
              makeWrapperArgs+=( "''${qtWrapperArgs[@]}" )
            '' + pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isLinux ''
              makeWrapperArgs+=( --set FONTCONFIG_FILE ${pkgs.makeFontsConf {
                fontDirectories = [ pkgs.dejavu_fonts ];
              }} )
            '';
            doInstallCheck = true;
            installCheckPhase = ''
              export XDG_CACHE_HOME="$TMPDIR/font-cache"
              QT_QPA_PLATFORM=offscreen "$out/bin/viewview" --smoke-test
            '';
            meta.mainProgram = "viewview";
          };
          bundle = if pkgs.stdenv.hostPlatform.isDarwin then
            import ./packaging/macos.nix { inherit pkgs python runtimeDependencies src; }
          else nix-appimage.lib.${system}.mkAppImage {
            program = "${application}/bin/viewview";
            name = "Viewview-${system}.AppImage";
          };
        in {
          packages = {
            default = application;
            viewview = application;
            inherit bundle;
          } // pkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux { appimage = bundle; }
            // pkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isDarwin { macos-app = bundle; };
          devShells.default = pkgs.mkShell {
            packages = [ environment pkgs.qt6.wrapQtAppsHook ];
            buildInputs = [ pkgs.qt6.qtbase ];
            shellHook = ''
              export QT_PLUGIN_PATH="${pkgs.qt6.qtbase}/${pkgs.qt6.qtbase.qtPluginPrefix}:''${QT_PLUGIN_PATH:-}"
            '';
          };
        });
    in {
      packages = nixpkgs.lib.mapAttrs (_: value: value.packages) perSystem;
      devShells = nixpkgs.lib.mapAttrs (_: value: value.devShells) perSystem;
    };
}
