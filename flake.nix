{
  description = "spotifython-cli";
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        spotifython = pkgs.python3.pkgs.callPackage ./spotifython.nix { };
      in {
        packages.default =
          pkgs.callPackage ./package.nix { inherit spotifython; };
      });
}
